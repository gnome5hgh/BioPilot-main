"""会话级轻量查询与清理（adapters 公开面）：给 mapper 委托与 service 用。

这里的函数都是「一次请求级」的读写——与会话装配（``build_memory``）无关，
不需要长期持有 manager：内部现取共享连接池。SQL 直接写在本层（适配层是
SQL 的家）；需要复用仓储语义的地方（删户、状态行删除）走同域仓储类。
"""
from __future__ import annotations

from biopilot.engine.memory.adapters.agent_state import MySqlAgentStateRepository
from biopilot.engine.memory.adapters.cursor import MySqlConsolidationCursorStore
from biopilot.engine.memory.adapters.database import MemoryDB
from biopilot.engine.memory.adapters.message import first_user_content

__all__ = [
    "get_title", "set_title", "list_history", "list_context_rows",
    "update_message_meta", "delete_conversation", "list_sessions",
    "mark_user_deleting", "delete_consolidation_cursor", "purge_user",
]


def get_title(user_id: str, conversation_id: str) -> str | None:
    """读取会话标题；无行返回 None。

    Args:
        user_id: 归属用户（行级隔离）。
        conversation_id: 会话标识。

    Returns:
        str | None：标题。
    """
    row = MemoryDB.shared().execute(
        "SELECT name FROM bio_agent_state WHERE agent_id=? AND user_id=?",
        (conversation_id, user_id)).fetchone()
    return None if row is None else row["name"]


def set_title(user_id: str, conversation_id: str, title: str) -> None:
    """设置会话标题（只在 name 为空时由调用方调用）。

    Args:
        user_id: 归属用户。
        conversation_id: 会话标识。
        title: 新标题。
    """
    MemoryDB.shared().execute(
        "UPDATE bio_agent_state SET name=? WHERE agent_id=? AND user_id=?",
        (title, conversation_id, user_id))


def list_history(user_id: str, conversation_id: str) -> list[dict]:
    """取一段会话的可见消息行（user/assistant，按 seq 正序）。

    Args:
        user_id: 归属用户。
        conversation_id: 会话标识。

    Returns:
        行 dict 列表（role/content/meta/created_at）。
    """
    return [dict(r) for r in MemoryDB.shared().execute(
        "SELECT role, content, meta, created_at FROM bio_message"
        " WHERE agent_id=? AND user_id=? AND role IN ('user','assistant')"
        " AND content IS NOT NULL AND content != ''"
        " ORDER BY seq", (conversation_id, user_id)).fetchall()]


def list_context_rows(user_id: str, conversation_id: str) -> list[dict]:
    """取上下文用量估算所需的角色/正文/工具调用列。

    Args:
        user_id: 归属用户。
        conversation_id: 会话标识。

    Returns:
        行 dict 列表（role/content/tool_calls）。
    """
    return [dict(r) for r in MemoryDB.shared().execute(
        "SELECT role, content, tool_calls FROM bio_message"
        " WHERE agent_id=? AND user_id=?",
        (conversation_id, user_id)).fetchall()]


def update_message_meta(user_id: str, conversation_id: str,
                        prefix_len: int, prefix: str, meta_json: str) -> None:
    """按「会话 + 归属 + role=user + 正文前缀」回填最近一行用户消息的 meta。

    Args:
        user_id: 归属用户。
        conversation_id: 会话标识。
        prefix_len: 前缀长度（LEFT 比较用）。
        prefix: 正文前缀。
        meta_json: 已序列化的附件元数据 JSON。
    """
    MemoryDB.shared().execute(
        "UPDATE bio_message SET meta=? WHERE agent_id=? AND user_id=?"
        " AND role='user' AND LEFT(content, ?)=?"
        " ORDER BY seq DESC LIMIT 1",
        (meta_json, conversation_id, user_id, prefix_len, prefix))


def delete_conversation(user_id: str, conversation_id: str) -> int:
    """删除一个会话：消息行 + 游标行 + 状态行（归属双条件）。

    Args:
        user_id: 归属用户。
        conversation_id: 会话标识。

    Returns:
        int：agent_state 删除行数（0 = 会话不存在或不归属该用户）。
    """
    db = MemoryDB.shared()
    db.execute("DELETE FROM bio_message WHERE agent_id=? AND user_id=?",
               (conversation_id, user_id))
    db.execute(
        "DELETE c FROM bio_memory_consolidation_cursor c"
        " JOIN bio_agent_state a ON c.agent_id=a.agent_id"
        " WHERE a.agent_id=? AND (a.user_id=? OR a.user_id LIKE CONCAT('deleting:', ?))",
        (conversation_id, user_id, user_id))
    return MySqlAgentStateRepository(db).delete_conversation(user_id, conversation_id)


def list_sessions(user_id: str, limit: int = 10,
                  project_id: str | None = None) -> list[dict]:
    """列出该用户的历史会话（新→旧），供会话恢复菜单展示。

    Args:
        user_id: 归属用户。
        limit: 最多返回的会话数。
        project_id: 项目过滤（None 不过滤）。

    Returns:
        dict 列表：agent_id / created_at / message_count / preview。
    """
    db = MemoryDB.shared()
    state = MySqlAgentStateRepository(db)
    sessions = []
    for r in state.list_session_rows(user_id, limit, project_id):
        agent_id = r["agent_id"]
        first = first_user_content(db, agent_id)
        sessions.append({
            "agent_id": agent_id,
            "created_at": r["created_at"],
            "message_count": db.execute(
                "SELECT COUNT(*) AS c FROM bio_message WHERE agent_id=?",
                (agent_id,)).fetchone()["c"],
            "preview": (str(first).strip().replace("\n", " ")[:60] if first else ""),
        })
    return sessions


def mark_user_deleting(target_id: str) -> None:
    """删户第一阶段：把会话归属改名为 deleting:<uid>，让新请求不再复用。

    Args:
        target_id: 目标用户 id。
    """
    MySqlAgentStateRepository(MemoryDB.shared()).mark_user_deleting(target_id)


def delete_consolidation_cursor(target_id: str) -> None:
    """删户清理：按 agent_state 归属清理整合游标（游标表没有 user_id 列）。

    Args:
        target_id: 目标用户 id。
    """
    MySqlConsolidationCursorStore(MemoryDB.shared()).delete_for_user(target_id)


def purge_user(target_id: str) -> None:
    """删户物理清理：清空该用户的记忆域数据（幂等，可重复执行）。

    覆盖 bio_message / bio_memory_block / bio_memory_block_history /
    bio_agent_state（含 mark-deleting 改名后的行）与整合游标。

    Args:
        target_id: 目标用户 id。
    """
    db = MemoryDB.shared()
    for table in ("bio_message", "bio_memory_block", "bio_memory_block_history"):
        db.execute(f"DELETE FROM {table} WHERE user_id=?", (target_id,))
    MySqlConsolidationCursorStore(db).delete_for_user(target_id)
    MySqlAgentStateRepository(db).delete_by_user(target_id)
