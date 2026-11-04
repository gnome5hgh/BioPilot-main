"""会话历史、删除与上下文用量的 HTTP 契约。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HistoryMessage(BaseModel):
    """历史回放的一条消息。"""

    role: str
    content: str
    created_at: Any = None
    attachments: list[dict[str, Any]] | None = None


class HistoryResponse(BaseModel):
    """``GET /chat/history`` 的响应。"""

    messages: list[HistoryMessage]


class ContextUsageParts(BaseModel):
    """上下文窗口用量的分解。"""

    total: int
    limit: int
    parts: dict[str, int]


class ContextUsageResponse(BaseModel):
    """``GET /chat/context-usage`` 的响应。"""

    usage: ContextUsageParts | None = None


class DeleteSessionResponse(BaseModel):
    """``DELETE /chat/session`` 的响应。"""

    status: str = "ok"
