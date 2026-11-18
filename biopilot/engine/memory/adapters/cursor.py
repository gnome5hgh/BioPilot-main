"""整合消费权游标（bio_memory_consolidation_cursor）的 MySQL 实现。

游标按 agent_id 键控（表没有 user_id 列）；行存在即「该 agent 已消费到
cursor 条」。跨进程防双消费由命名锁承担，这里只管游标行的读写。
"""
from __future__ import annotations

from datetime import datetime, timezone

from biopilot.engine.memory.adapters.database import MemoryDB

__all__ = ["MySqlConsolidationCursorStore"]


class MySqlConsolidationCursorStore:
    """``ConsolidationCursorStore`` 的 MySQL 实现。"""

    def __init__(self, db: MemoryDB):
        """绑定连接。

        Args:
            db: 数据库连接（需已初始化）。
        """
        self._db = db

    def ensure(self, agent_id: str) -> None:
        """初始化游标行为 0（新会话从 0 开始消费；已有行保持不动）。

        新会话必须显式写游标行，否则整合器会把「行不存在」当成「历史已消费」
        而回填到当前消息数，导致第一轮内容永远不进长期记忆。

        Args:
            agent_id: 会话标识。
        """
        self._db.execute(
            "INSERT IGNORE INTO bio_memory_consolidation_cursor"
            " (agent_id, `cursor`, updated_at) VALUES (?,?,?)",
            (agent_id, 0, datetime.now(timezone.utc).isoformat()))

    def load(self, agent_id: str) -> int | None:
        """读当前游标；行不存在返回 None。"""
        row = self._db.execute(
            "SELECT `cursor` FROM bio_memory_consolidation_cursor WHERE agent_id=?",
            (agent_id,)).fetchone()
        return None if row is None else int(row["cursor"])

    def save(self, agent_id: str, cursor: int) -> None:
        """推进游标（REPLACE 幂等）。"""
        self._db.execute(
            "REPLACE INTO bio_memory_consolidation_cursor (agent_id, `cursor`, updated_at)"
            " VALUES (?,?,?)",
            (agent_id, cursor, datetime.now(timezone.utc).isoformat()))

    def delete_for_user(self, target_id: str) -> None:
        """按 agent_state 归属清理游标（含 mark-deleting 改名后的行）。

        Args:
            target_id: 归属用户 id。
        """
        self._db.execute(
            "DELETE c FROM bio_memory_consolidation_cursor c"
            " JOIN bio_agent_state a ON c.agent_id=a.agent_id"
            " WHERE a.user_id=? OR a.user_id LIKE CONCAT('deleting:', ?)",
            (target_id, target_id))
