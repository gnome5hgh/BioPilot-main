"""共享记忆库连接（懒建单例）。"""
from __future__ import annotations

_db_instance = None


def shared_db():
    """适配层共享的 MemoryDB（懒建；标题更新等轻量 SQL 用）。"""
    global _db_instance
    if _db_instance is None:
        from biopilot.engine.memory.storage.database import MemoryDB
        _db_instance = MemoryDB()
    return _db_instance
