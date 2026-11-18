"""skills 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块）一律经本文件或包根别名使用 skills：
注册表、会话工具合并、预批准、用户技能物化。出向实现（``bio_skill`` 只读 SQL、
平台包拉取）同住 ``adapters/``，同属公开面。
"""
from biopilot.engine.skills.adapters.skill_store import MySqlSkillSource
from biopilot.engine.skills.application.assembly import apply_pre_approval, merge_tools
from biopilot.engine.skills.application.layout import user_skills_cache_dir
from biopilot.engine.skills.application.registry import SkillRegistry
from biopilot.engine.skills.application.user_skills import sync_user_skills
from biopilot.engine.skills.config import SkillConfig
from biopilot.engine.skills.domain.ports import SkillPackageSource, SkillSource

__all__ = [
    "SkillRegistry", "SkillConfig", "apply_pre_approval", "merge_tools",
    "sync_user_skills", "user_skills_cache_dir",
    "SkillSource", "SkillPackageSource", "MySqlSkillSource",
    "build_skill_source",
]


def build_skill_source(db) -> MySqlSkillSource:
    """构造技能清单端口（模块对外唯一的组装入口）。

    Args:
        db: MemoryDB 连接池（只读 bio_skill）。

    Returns:
        MySqlSkillSource。
    """
    return MySqlSkillSource(db)
