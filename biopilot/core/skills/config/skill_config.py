"""Skill 插件配置：`SkillRegistry` 扫描技能目录的产物。

与顶层 `biopilot/config/` 分工：那里是「与 config.yaml 同构、可经 env 派生」的
全局可调参数；这里是**组件自己的行为参数**，由注册表在加载时构造，不进 config.yaml。

平台只支持 agentskills.io 标准形态包：skill 只携带指令与资源，不携带可执行工具。
"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillConfig:
    """单个 Skill 的完整配置，由 SkillRegistry 从 skills/<name>/ 目录加载。

    字段来源::

        name            ← SKILL.md frontmatter "name"（必须等于目录名，agentskills.io 规范）
        description     ← SKILL.md frontmatter "description"（做什么 + 何时触发，L1 消费）
        instructions    ← SKILL.md 正文（frontmatter 后的 Markdown，L2 按需加载）
        metadata        ← SKILL.md frontmatter "metadata"（version/author 等，清单展示用）
        path            ← skill 目录路径（load_resource 读取资源的围栏根）

    Attributes:
        name: str，skill 名（须等于目录名）
        description: str，做什么 + 何时触发（L1 清单消费）
        instructions: str，SKILL.md 正文（L2 按需加载）
        metadata: dict，frontmatter metadata（version/author 等）
        path: Path | None，skill 目录（L3 资源读取的围栏根）
    """

    name: str
    description: str = ""
    instructions: str = ""
    metadata: dict = field(default_factory=dict)
    path: Path | None = None
