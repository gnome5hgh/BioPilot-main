"""``bio_rag_index_state`` 的删户清理 SQL。"""
from __future__ import annotations


def delete_by_user(db, user_id: str):
    """删除某用户的索引状态行。"""
    return db.execute(
        "DELETE FROM bio_rag_index_state WHERE user_id=?", (user_id,))
