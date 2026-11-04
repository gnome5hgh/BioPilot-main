"""对话与确认端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from biopilot.api.deps import get_services, require_user
from biopilot.schema.chat import ChatStreamRequest, ConfirmRequest, ConfirmResponse
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/confirm", response_model=ConfirmResponse)
async def chat_confirm(
    req: ConfirmRequest,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """回传确认决定（approved=true/false），唤醒等待中的 run。"""
    return await services.chat.confirm(
        user_id, req.conversation_id, req.req_id, req.approved)


@router.post("/stream")
async def chat_stream(
    request: Request,
    req: ChatStreamRequest,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> StreamingResponse:
    """对话流：SSE 帧序列（token/tool/round/done）。"""
    iterator = await services.chat.stream(
        user_id, req.task, req.conversation_id, req.project_id,
        [a.model_dump() for a in req.attachments], request.is_disconnected)
    return StreamingResponse(iterator, media_type="text/event-stream")
