"""Skill 服务：注册表、准入安装与装配并入。

`SkillConfig`（插件配置实体）在 `../domain/`。
"""
from biopilot.core.skills.services.assembly import apply_pre_approval, merge_tools
from biopilot.core.skills.services.install import (
    enable_skill,
    install_skill,
    list_skills_command,
    load_lock,
    uninstall_skill,
    update_skill,
)
from biopilot.core.skills.services.registry import SkillRegistry

__all__ = [
    "SkillRegistry",
    "merge_tools",
    "install_skill",
    "update_skill",
    "uninstall_skill",
    "enable_skill",
    "list_skills_command",
    "load_lock",
]
