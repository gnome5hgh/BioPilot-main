"""``bio_message`` 的请求级数据访问（委托层）。

SQL 都在 memory 模块的适配层（``engine/memory/adapters``）；本模块只保留
service 侧的访问点名，逐条委托——引擎表不再有第二份 SQL。
"""
from __future__ import annotations

from biopilot.engine.memory.adapters import conversation as memory_conversation


def select_history(user_id: str, conversation_id: str):
    """取一段会话的可见消息（user/assistant，按 seq 正序）。"""
    return memory_conversation.list_history(user_id, conversation_id)


def select_context_rows(user_id: str, conversation_id: str):
    """取上下文用量估算所需的角色/正文/工具调用列。"""
    return memory_conversation.list_context_rows(user_id, conversation_id)


def update_user_message_meta(user_id: str, conversation_id: str,
                             prefix_len: int, prefix: str, meta_json: str):
    """按「会话 + 归属 + role=user + 正文前缀」回填最近一行用户消息的 meta。"""
    return memory_conversation.update_message_meta(
        user_id, conversation_id, prefix_len, prefix, meta_json)
