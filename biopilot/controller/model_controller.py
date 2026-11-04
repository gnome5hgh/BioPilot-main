"""模型清单与会话级模型选择端点。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from biopilot.api.deps import get_services, require_user
from biopilot.schema.model import (
    ModelSelectRequest,
    ModelSelectResponse,
    ModelsResponse,
)
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelsResponse)
async def models_list(
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """可选模型清单：主模型 + runtime.models 配置条目（不回传 key）。"""
    return await asyncio.to_thread(services.model.list, user_id)


@router.post("/select", response_model=ModelSelectResponse)
async def models_select(
    req: ModelSelectRequest,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """会话级模型选择：本用户后续 run 用所选模型。"""
    return await asyncio.to_thread(services.model.select, user_id, req.name)
