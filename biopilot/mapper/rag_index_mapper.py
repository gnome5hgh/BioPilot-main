"""``bio_rag_index_state`` 的删户清理（委托层）。"""
from __future__ import annotations

from biopilot.engine.rag.adapters.paper_status import delete_index_state_by_user
from biopilot.mapper.base import shared_db


def delete_by_user(user_id: str):
    """删除某用户的索引状态行。"""
    return delete_index_state_by_user(shared_db(), user_id)
