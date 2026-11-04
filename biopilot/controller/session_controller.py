"""会话历史、删除与上下文用量端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from biopilot.api.deps import get_services, require_user
from biopilot.schema.session import (
    ContextUsageResponse,
    DeleteSessionResponse,
    HistoryResponse,
)
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/history", response_model=HistoryResponse,
            response_model_exclude_none=True)
async def chat_history(
    conversation_id: str = "",
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """取一段会话的可见历史（user/assistant 两条腿，按时间正序）。"""
    return services.session.history(user_id, conversation_id)


@router.delete("/session", response_model=DeleteSessionResponse)
async def chat_session_delete(
    conversation_id: str = "",
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """删除一个会话：消息行 + agent_state 行（归属双条件）。"""
    return services.session.delete(user_id, conversation_id)


@router.get("/context-usage", response_model=ContextUsageResponse)
async def chat_context_usage(
    conversation_id: str = "",
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """当前会话的上下文窗口用量分解。"""
    return services.session.context_usage(user_id, conversation_id)
