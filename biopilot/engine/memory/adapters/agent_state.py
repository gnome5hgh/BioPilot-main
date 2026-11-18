"""bio_agent_state 表的 SQL 访问（适配层）。

AgentManager（应用层）负责归属防护、白名单与领域对象组装；本模块只做
「领域参数 ⇄ SQL 行」的翻译：行读写、整合游标初始化与会话列表查询。
模块级函数 + ``MySqlAgentStateRepository``（``AgentStateRepository`` 端口的
MySQL 实现）。建表 DDL 在 ``database._SCHEMA`` 统一维护。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from biopilot.engine.memory.adapters.database import MemoryDB
from biopilot.engine.memory.domain.schemas.agent import AgentState
from biopilot.engine.memory.domain.schemas.memory import Memory

__all__ = [
    "fetch_owner", "fetch_row", "replace_row", "init_cursor",
    "update_fields", "list_session_rows", "MySqlAgentStateRepository",
]


def fetch_owner(db, agent_id: str) -> str | None:
    """读一行当前的归属 user_id；行不存在返回 None。

    Args:
        db: MemoryDB。
        agent_id: 会话标识（表主键）。

    Returns:
        str | None：归属 user_id；无该行时 None。
    """
    row = db.execute("SELECT user_id FROM bio_agent_state WHERE agent_id=?",
                     (agent_id,)).fetchone()
    return None if row is None else row["user_id"]


def fetch_row(db, agent_id: str, user_id: str | None = None) -> dict | None:
    """按 id 取一行（可选归属过滤）；无匹配返回 None。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。
        user_id: 归属过滤（None 不过滤；传入则要求行归属该用户）。

    Returns:
        dict | None：整行（列名 → 值）；无匹配时 None。
    """
    if user_id is None:
        cur = db.execute("SELECT * FROM bio_agent_state WHERE agent_id=?", (agent_id,))
    else:
        cur = db.execute("SELECT * FROM bio_agent_state WHERE agent_id=? AND user_id=?",
                         (agent_id, user_id))
    row = cur.fetchone()
    return None if row is None else dict(row)


def replace_row(db, agent_id: str, user_id: str, name: str | None,
                project_id: str | None) -> None:
    """REPLACE INTO 幂等写入一行（按主键覆盖），初始 message_ids 为空列表。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。
        user_id: 归属用户（行级隔离键）。
        name: 会话名（可 None）。
        project_id: 归属项目（可 None）。
    """
    db.execute(
        "REPLACE INTO bio_agent_state (agent_id, user_id, name, message_ids, created_at,"
        " project_id) VALUES (?,?,?,?,?,?)",
        (agent_id, user_id, name, "[]",
         datetime.now(timezone.utc).isoformat(), project_id))


_UPDATABLE_COLUMNS = frozenset({
    "name", "description", "system", "model", "context_window_limit", "message_ids",
})


def update_fields(db, agent_id: str, updates: dict[str, str]) -> None:
    """按「列名 → 已序列化值」逐列更新一行（键来自应用层白名单）。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。
        updates: 列名 → 值（应用层已把 list/dict 序列化为 JSON 字符串）。

    Raises:
        ValueError: 列名不在本表可更新集合内（适配器侧二次把关，f-string 拼列名
            只接受这份闭集，不信任调用方白名单的跨层纪律）。
    """
    for key, val in updates.items():
        if key not in _UPDATABLE_COLUMNS:
            raise ValueError(f"bio_agent_state 不允许更新列: {key}")
        db.execute(f"UPDATE bio_agent_state SET {key}=? WHERE agent_id=?",
                   (val, agent_id))


def list_session_rows(db, user_id: str, limit: int,
                      project_id: str | None = None) -> list[dict]:
    """列出该用户的会话行（新→旧），可选项目过滤。

    Args:
        db: MemoryDB。
        user_id: 归属用户（行级隔离）。
        limit: 最多返回的会话数。
        project_id: 项目过滤（None 不过滤）。

    Returns:
        dict 列表，每项含 agent_id 与 created_at。
    """
    if project_id is not None:
        rows = db.execute(
            "SELECT agent_id, created_at FROM bio_agent_state"
            " WHERE user_id=? AND project_id=?"
            " ORDER BY created_at DESC, agent_id LIMIT ?", (user_id, project_id, limit)).fetchall()
    else:
        rows = db.execute(
            "SELECT agent_id, created_at FROM bio_agent_state WHERE user_id=?"
            " ORDER BY created_at DESC, agent_id LIMIT ?", (user_id, limit)).fetchall()
    return [dict(r) for r in rows]




class MySqlAgentStateRepository:
    """``AgentStateRepository`` 的 MySQL 实现：状态行读写 + 删户/删会话 SQL。

    行 → AgentState 的翻译收在本类；``memory`` 字段不来自 DB（由应用层从
    块表动态构建），这里填空 Memory 占位。
    """

    def __init__(self, db: MemoryDB):
        """绑定连接。

        Args:
            db: 数据库连接（需已初始化）。
        """
        self._db = db

    def owner(self, agent_id: str) -> str | None:
        """读一行当前的归属 user_id；行不存在返回 None。"""
        return fetch_owner(self._db, agent_id)

    def get(self, agent_id: str, user_id: str | None = None) -> AgentState | None:
        """按 id 取会话状态（可选归属过滤）；无匹配返回 None。

        Args:
            agent_id: 会话标识。
            user_id: 归属过滤（None 不过滤）。
        """
        row = fetch_row(self._db, agent_id, user_id)
        if row is None:
            return None
        return AgentState(
            agent_id=row["agent_id"],
            name=row["name"],
            description=row["description"],
            system=row["system"],
            model=row["model"],
            context_window_limit=row["context_window_limit"],
            message_ids=json.loads(row["message_ids"]) if row["message_ids"] else [],
            memory=Memory(blocks=[]),
            created_at=row["created_at"],
            user_id=str(row["user_id"]),
            project_id=row.get("project_id"),
        )

    def replace(self, agent_id: str, user_id: str, name: str | None,
                project_id: str | None) -> None:
        """REPLACE INTO 幂等写入一行。"""
        replace_row(self._db, agent_id, user_id, name, project_id)

    def update_fields(self, agent_id: str, updates: dict[str, str]) -> None:
        """按「列名 → 已序列化值」逐列更新一行。"""
        update_fields(self._db, agent_id, updates)

    def list_session_rows(self, user_id: str, limit: int,
                          project_id: str | None = None) -> list[dict]:
        """列出该用户的会话行（新→旧），可选项目过滤。"""
        return list_session_rows(self._db, user_id, limit, project_id)

    def mark_user_deleting(self, target_id: str) -> None:
        """删户第一阶段：把归属改名为 deleting:<uid>，让新请求不再复用。"""
        self._db.execute(
            "UPDATE bio_agent_state SET user_id=CONCAT('deleting:', user_id)"
            " WHERE user_id=? AND user_id NOT LIKE 'deleting:%'", (target_id,))

    def delete_conversation(self, user_id: str, conversation_id: str) -> int:
        """删除一个会话的状态行；返回删除行数。"""
        return self._db.execute(
            "DELETE FROM bio_agent_state WHERE agent_id=? AND user_id=?",
            (conversation_id, user_id)).rowcount

    def delete_by_user(self, target_id: str) -> None:
        """删除该用户的全部状态行（含 mark-deleting 改名后的行）。"""
        self._db.execute(
            "DELETE FROM bio_agent_state WHERE user_id=?"
            " OR user_id LIKE CONCAT('deleting:', ?)", (target_id, target_id))
