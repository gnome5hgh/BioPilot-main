# biopilot/core/skills/services/layout.py
"""用户技能缓存目录布局。

用户技能由平台技能包（OSS）物化到 ``<workspace>/users/<uid>/skills``——本地目录
只是缓存，删掉后可随时重建，不是真相源。内置流程已并入 agent 的 AGENT.md，
不再有「内置技能目录」。
"""

import re
from pathlib import Path


def safe_user_component(user_id: str) -> str:
    """把用户 id 归一化成可安全拼进路径的片段。

    Args:
        user_id: 原始用户标识。

    Returns:
        只保留字母/数字/下划线/连字符的片段；空值回退 ``unknown``。
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(user_id or "")) or "unknown"


def user_skills_cache_dir(workspace: str, user_id: str) -> Path:
    """返回某用户的技能缓存目录（``<workspace>/users/<uid>/skills``）。

    Args:
        workspace: 引擎运行时数据根（配置项 ``runtime.workspace``）。
        user_id: 归属用户。

    Returns:
        用户技能缓存目录路径（不保证存在）。
    """
    return Path(workspace) / "users" / safe_user_component(user_id) / "skills"
