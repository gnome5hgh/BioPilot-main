"""配置派生路径的薄封装（保留测试可替换的模块级名字）。"""
from __future__ import annotations


def cfg_user_cache_root() -> str:
    """按用户隔离的派生缓存根（附件副本与技能物化的落点）。"""
    from biopilot.config import BioPilotConfig, user_cache_root
    return str(user_cache_root(BioPilotConfig.from_env()))
