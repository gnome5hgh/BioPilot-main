"""共享记忆库连接（转发到 MemoryDB.shared 的按 DSN 单例）。"""
from __future__ import annotations


def shared_db():
    """适配层共享的 MemoryDB（标题更新等轻量 SQL 与会话装配同一口池）。"""
    from biopilot.engine.memory.adapters.database import MemoryDB
    return MemoryDB.shared()
