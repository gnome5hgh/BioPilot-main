"""删户清理相关的通用删除 SQL。"""
from __future__ import annotations

from biopilot.mapper import message_mapper


def delete_from_table(db, table: str, user_id: str):
    """删除某张带 ``user_id`` 列的表里属于该用户的全部行。"""
    return message_mapper.delete_by_user(db, table, user_id)
