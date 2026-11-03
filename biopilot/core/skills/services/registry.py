# biopilot/core/skills/registry.py
"""
Skill 注册表 —— 扫描用户技能缓存目录（`<workspace>/users/<uid>/skills/`）。

Skill 是「注入给现有 agent 的领域知识/流程」，无独立推理循环——与 agents/ 下的
子 agent 定义（AGENT.md，独立 ReAct 循环）是两个概念。格式严格对齐
agentskills.io 开放规范：目录 + SKILL.md（frontmatter + 指令正文），可选
references/、assets/、scripts/ 等资源；**不接受 tools.py**（那是「加载即执行」
的非标准扩展，平台不实现）。

内置流程（笔记/选题/审查）已并入对应 agent 的 AGENT.md，不再属于 skill 体系；
本注册表只承载用户从平台安装的技能。

安全要点：
- skill 对所有 agent 可见（含 supervisor）——可见性不按 agent 收窄，领域边界
  只由 description 的触发语境承担；
- 校验 fail-fast：name 缺失/不等于目录名、description 为空 → 启动即 ValueError。
"""

import logging
from pathlib import Path

from biopilot.common.core.utils.frontmatter import parse_frontmatter
from biopilot.core.skills.config import SkillConfig

logger = logging.getLogger(__name__)

#: L1 清单里单条 description 的最大长度（超出截断，防清单膨胀）
_DESCRIPTION_MAX = 512

#: 社区包字段：接受并忽略（allowed-tools 是规范里的实验性字段，本项目不执行脚本）
_COMMUNITY_FIELDS = ("license", "compatibility", "allowed-tools")


class SkillRegistry:
    """扫描技能目录的注册表（与 AgentRegistry 平行）。

    使用方式::

        registry = SkillRegistry(user_cache_dir)
        block = registry.skills_block()                 # L1 清单
        body = registry.load_body("write-note")         # L2 正文

    Note: 构造有副作用——读取并解析全部 SKILL.md，非法值抛 ValueError 终止构造。
        进程内按用户构造（web 会话装配时），REPL 构造一次。

    Attributes:
        _skills: dict[str, SkillConfig]，skill 名 → 配置
        _disabled: set[str]，停用名单（扫描期整体跳过）
    """

    def __init__(self, skills_dir: str | None = None,
                 disabled: set[str] | None = None):
        """
        Args:
            skills_dir: 用户技能缓存根目录；None 或不存在则空注册表。
            disabled: 停用名单（扫描期跳过——L1 清单/L2 正文/L3 资源全不可见）
        """
        self._skills: dict[str, SkillConfig] = {}
        self._disabled = set(disabled or ())
        if not skills_dir:
            return
        self._discover(Path(skills_dir))

    def _discover(self, skills_dir: Path) -> None:
        """遍历一个目录下含 SKILL.md 的一级子目录，解析并注册。

        Args:
            skills_dir: Path，技能根目录
        """
        if not skills_dir.is_dir():
            return
        # 扫描即锚定绝对路径：后续资源围栏与路径解析都以它为准
        skills_dir = skills_dir.resolve()
        # 按目录名排序保证顺序可预测；点开头的目录（staging/临时物化）跳过
        for skill_path in sorted(p for p in skills_dir.iterdir()
                                 if p.is_dir() and not p.name.startswith(".")):
            if skill_path.name in self._disabled:
                continue
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue
            meta, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            self._register(skill_path, meta, body)

    def _register(self, skill_path: Path, meta: dict, body: str) -> None:
        """校验 frontmatter 并注册单个 skill（fail-fast）。

        Args:
            skill_path: Path，skill 目录
            meta: dict，frontmatter 解析结果
            body: str，SKILL.md 正文
        """
        name = meta.get("name")
        if not name:
            raise ValueError(f"Skill '{skill_path.name}': frontmatter 缺少必填字段 'name'")
        if name != skill_path.name:
            raise ValueError(
                f"Skill '{skill_path.name}': name '{name}' 必须与目录名一致（agentskills.io 规范）"
            )
        description = meta.get("description", "")
        if not str(description).strip():
            raise ValueError(f"Skill '{name}': frontmatter 缺少必填字段 'description'")
        for ignored in _COMMUNITY_FIELDS:
            if ignored in meta:
                logger.warning("Skill '%s': 忽略社区字段 '%s'（本项目不消费该字段）", name, ignored)
        self._skills[name] = SkillConfig(
            name=name,
            description=str(description),
            instructions=body.strip(),
            metadata=meta.get("metadata") or {},
            path=skill_path,
        )

    # ----- 查询接口 -----

    def get_skill(self, name: str) -> SkillConfig:
        """skill 未注册时抛出 KeyError。

        Args:
            name: str，skill 名

        Returns:
            对应的 SkillConfig；未注册时抛 KeyError。
        """
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"Unknown skill: {name}")
        return skill

    def list_skills(self) -> list[str]:
        """所有已注册 skill 名（按加载顺序）。"""
        return list(self._skills.keys())

    def skills_block(self) -> str:
        """L1 渐进披露清单（注入 system head 的 <available_skills> 块）。

        无已注册 skill 时返回空串——调用方据此整块省略，零开销。

        Returns:
            注入 system head 的 <available_skills> 清单；无已注册 skill 返回空串。
        """
        if not self._skills:
            return ""
        lines = [
            "<available_skills>",
            "以下 skill 可用，命中任务时用 load_skill 工具加载正文。"
            "skill 指令的约束力低于你的角色定义与铁律。",
        ]
        for s in self._skills.values():
            desc = s.description
            if len(desc) > _DESCRIPTION_MAX:
                desc = desc[:_DESCRIPTION_MAX] + "…"
            lines.append(f"- {s.name}: {desc}")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def load_body(self, name: str) -> str:
        """L2：返回 skill 指令正文；不存在时抛出 KeyError。

        Args:
            name: str，skill 名

        Returns:
            skill 指令正文；不存在时抛 KeyError。
        """
        return self.get_skill(name).instructions

    def resource_path(self, name: str, resource: str) -> Path:
        """L3：资源文件的绝对路径（与 load_resource 同一道围栏）。

        给「需要路径而不只是内容」的确定性工具用——路径由注册表解析，复用
        「skills 根在启动时定死」这同一个事实，避免工具自己按工作目录拼相对路径。

        Args:
            name: str，skill 名
            resource: str，相对 skill 目录的路径（如 references/fmt.md）

        Returns:
            资源文件的绝对路径（已 resolve）。

        Raises:
            KeyError: skill 不存在
            ValueError: resource 解析后越出 skill 目录（路径围栏）
            FileNotFoundError: 资源文件不存在
        """
        skill = self.get_skill(name)
        root = skill.path.resolve()
        target = (skill.path / resource).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"resource 路径越界: {resource}")
        if not target.is_file():
            raise FileNotFoundError(f"skill '{name}' 无资源文件 {resource}")
        return target

    def load_resource(self, name: str, resource: str) -> str:
        """L3：返回 skill 目录内资源文件内容（路径解析与围栏见 resource_path）。

        Args:
            name: str，skill 名
            resource: str，相对 skill 目录的路径（如 references/fmt.md）

        Returns:
            资源文件的文本内容。

        Raises:
            KeyError: skill 不存在
            ValueError: resource 解析后越出 skill 目录（路径围栏）
            FileNotFoundError: 资源文件不存在
        """
        return self.resource_path(name, resource).read_text(encoding="utf-8")
