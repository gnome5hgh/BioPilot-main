"""``bio_agent_state`` 的请求级数据访问（委托层）。

SQL 与操作都在 memory 模块的适配层（``engine/memory/adapters``）；本模块只保留
service 侧的访问点名，逐条委托——引擎表不再有第二份 SQL。
"""
from __future__ import annotations

from biopilot.engine.memory.adapters import conversation as memory_conversation


def select_name(conversation_id: str, user_id: str):
    """读取会话标题行（事务外轻量查询）。"""
    return memory_conversation.get_title(user_id, conversation_id)


def update_name(title: str, conversation_id: str, user_id: str):
    """设置会话标题（只在 name 为空时调用）。"""
    return memory_conversation.set_title(user_id, conversation_id, title)


def mark_deleting(target_id: str):
    """删户第一阶段：把归属改名为 deleting:<uid>，让新请求不再复用。"""
    return memory_conversation.mark_user_deleting(target_id)


def delete_consolidation_cursor(target_id: str):
    """按 agent_state 归属清理整合游标（游标表没有 user_id 列）。"""
    return memory_conversation.delete_consolidation_cursor(target_id)


def delete_by_user(target_id: str):
    """删除该用户的 agent_state 行（含 mark-deleting 改名后的行）。"""
    return memory_conversation.purge_user(target_id)
