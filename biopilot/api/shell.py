"""兼容旧导入路径：终端实现已迁到 ``service/impl/terminal_service_impl.py``。"""
from __future__ import annotations

from biopilot.service.impl.terminal_service_impl import (
    BUFFER_LIMIT,
    IDLE_SECONDS,
    ShellManager,
    ShellSession,
)

__all__ = ["ShellSession", "ShellManager", "BUFFER_LIMIT", "IDLE_SECONDS"]
