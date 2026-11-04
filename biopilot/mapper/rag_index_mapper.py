"""``bio_rag_index_state`` 的删户清理 SQL。"""
from __future__ import annotations


def delete_domain(db, user_domain: str):
    """删除某用户域的索引状态行。"""
    return db.execute(
        "DELETE FROM bio_rag_index_state WHERE user_domain=?", (user_domain,))
