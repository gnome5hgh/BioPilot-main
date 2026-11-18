"""Skill 域包 —— 技能发现、运行时消费与用户技能缓存。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：``SkillRegistry`` /
``SkillConfig`` / ``merge_tools`` / ``apply_pre_approval`` / ``sync_user_skills``。
管理面（安装/启停/更新/卸载）在 Java 的 bio-skill 模块；引擎只做只读消费。
模块外一律经 ``adapters.api`` 或本别名 import。
"""
from biopilot.engine.skills.adapters.api import *  # noqa: F401,F403
from biopilot.engine.skills.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
