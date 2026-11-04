"""知识库运行时端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from biopilot.api.deps import get_services, require_user
from biopilot.schema.kb import (
    KbChunksResponse,
    KbReindexRequest,
    KbReindexResponse,
    KbSearchRequest,
    KbSearchResponse,
)
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/kb", tags=["kb"])


@router.post("/reindex", response_model=KbReindexResponse)
async def kb_reindex(
    req: KbReindexRequest | None = None,
    force: bool = False,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """重建知识库：默认只补排队/失败/缺文件的论文；force=true 时全部重扫。"""
    return await services.kb.reindex(user_id, force)


@router.post("/search", response_model=KbSearchResponse)
async def kb_search(
    req: KbSearchRequest,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """知识库试检索。"""
    return await services.kb.search(user_id, req)


@router.get("/papers/{paper_id}/chunks", response_model=KbChunksResponse)
async def kb_paper_chunks(
    paper_id: str,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """读取一篇论文的全部分块。"""
    return await services.kb.chunks(user_id, paper_id)
