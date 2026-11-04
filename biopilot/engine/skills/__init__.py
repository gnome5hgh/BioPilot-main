# biopilot/engine/skills/__init__.py
"""Skill 域包 —— 技能发现、运行时消费与用户技能缓存。

公共出口（下游一律 `from biopilot.engine.skills import ...`）：
- ``SkillRegistry`` / ``SkillConfig`` ← registry（发现/校验/渐进披露）
- ``merge_tools`` / ``apply_pre_approval`` ← assembly（工具命名空间唯一性）
- ``sync_user_skills`` ← user_skills（把用户安装的技能物化成本地缓存）

管理面（安装/启停/更新/卸载）在 Java 的 bio-skill 模块；引擎只做只读消费。
"""

from biopilot.engine.skills.services.assembly import apply_pre_approval, merge_tools
from biopilot.engine.skills.services.layout import user_skills_cache_dir
from biopilot.engine.skills.services.registry import SkillRegistry
from biopilot.engine.skills.services.user_skills import sync_user_skills
from biopilot.engine.skills.config import SkillConfig

__all__ = [
    "SkillConfig",
    "SkillRegistry",
    "apply_pre_approval",
    "merge_tools",
    "sync_user_skills",
    "user_skills_cache_dir",
]
