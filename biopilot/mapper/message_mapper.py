"""``bio_message`` 的读写 SQL。"""
from __future__ import annotations


def select_history(db, user_id: str, conversation_id: str):
    """取一段会话的可见消息（user/assistant，按 seq 正序）。"""
    return db.execute(
        "SELECT role, content, meta, created_at FROM bio_message"
        " WHERE agent_id=? AND user_id=? AND role IN ('user','assistant')"
        " AND content IS NOT NULL AND content != ''"
        " ORDER BY seq", (conversation_id, user_id)).fetchall()


def delete_for_conversation(db, user_id: str, conversation_id: str):
    """删除一个会话的全部消息行。"""
    return db.execute("DELETE FROM bio_message WHERE agent_id=? AND user_id=?",
                      (conversation_id, user_id))


def select_context_rows(db, user_id: str, conversation_id: str):
    """取上下文用量估算所需的角色/正文/工具调用列。"""
    return db.execute(
        "SELECT role, content, tool_calls FROM bio_message"
        " WHERE agent_id=? AND user_id=?",
        (conversation_id, user_id)).fetchall()


def update_user_message_meta(db, user_id: str, conversation_id: str,
                             prefix_len: int, prefix: str, meta_json: str):
    """按「会话 + 归属 + role=user + 正文前缀」回填最近一行用户消息的 meta。"""
    return db.execute(
        "UPDATE bio_message SET meta=? WHERE agent_id=? AND user_id=?"
        " AND role='user' AND LEFT(content, ?)=?"
        " ORDER BY seq DESC LIMIT 1",
        (meta_json, conversation_id, user_id, prefix_len, prefix))


def delete_by_user(db, table: str, user_id: str):
    """删除某张表里属于该用户的全部行（删户清理用）。"""
    return db.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
