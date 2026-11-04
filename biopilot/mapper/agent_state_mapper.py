"""``bio_agent_state`` 与整合游标的 SQL。"""
from __future__ import annotations


def select_name(db, agent_id: str, user_id: str):
    """读取会话标题行（事务外轻量查询）。"""
    return db.execute(
        "SELECT name FROM bio_agent_state WHERE agent_id=? AND user_id=?",
        (agent_id, user_id)).fetchone()


def update_name(db, title: str, agent_id: str, user_id: str):
    """设置会话标题（只在 name 为空时调用）。"""
    return db.execute(
        "UPDATE bio_agent_state SET name=? WHERE agent_id=? AND user_id=?",
        (title, agent_id, user_id))


def delete_for_conversation(db, agent_id: str, user_id: str):
    """删除一个会话的 agent_state 行。"""
    return db.execute(
        "DELETE FROM bio_agent_state WHERE agent_id=? AND user_id=?",
        (agent_id, user_id))


def mark_deleting(db, target_id: str):
    """删户第一阶段：把归属改名为 deleting:<uid>，让新请求不再复用。"""
    return db.execute(
        "UPDATE bio_agent_state SET user_id=CONCAT('deleting:', user_id)"
        " WHERE user_id=? AND user_id NOT LIKE 'deleting:%'", (target_id,))


def delete_consolidation_cursor(db, target_id: str):
    """按 agent_state 归属清理整合游标（游标表没有 user_id 列）。"""
    return db.execute(
        "DELETE c FROM bio_memory_consolidation_cursor c"
        " JOIN bio_agent_state a ON c.agent_id=a.agent_id"
        " WHERE a.user_id=? OR a.user_id LIKE CONCAT('deleting:', ?)",
        (target_id, target_id))


def delete_by_user(db, target_id: str):
    """删除该用户的 agent_state 行（含 mark-deleting 改名后的行）。"""
    return db.execute(
        "DELETE FROM bio_agent_state WHERE user_id=?"
        " OR user_id LIKE CONCAT('deleting:', ?)", (target_id, target_id))
