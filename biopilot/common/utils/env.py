"""环境变量读取的薄封装。

单独成模块是为了让测试可以按「查找处」替换 ``os_env``，而不必改进程环境。
"""
from __future__ import annotations

import os


def os_env(key: str, default: str | None) -> str | None:
    """读取环境变量，不存在时返回默认值。"""
    return os.environ.get(key, default)
