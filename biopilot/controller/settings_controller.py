"""设置页端点。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from biopilot.api.deps import get_services, require_user
from biopilot.schema.settings import (
    SettingsHistoryResponse,
    SettingsPatchRequest,
    SettingsPatchResponse,
    SettingsRollbackRequest,
    SettingsRollbackResponse,
    SettingsSnapshotResponse,
)
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsSnapshotResponse)
async def settings_get(
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """返回设置页所需的全部数据：字段描述 + 有效值 + 来源 + 版本。"""
    return await asyncio.to_thread(services.settings.snapshot)


@router.get("/history", response_model=SettingsHistoryResponse)
async def settings_history(
    limit: int = 20,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """返回最近的配置保存历史。"""
    return await asyncio.to_thread(services.settings.history, limit)


@router.post("/rollback", response_model=SettingsRollbackResponse)
async def settings_rollback(
    req: SettingsRollbackRequest,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """回滚到指定历史版本；回滚动作本身也会记一条历史。"""
    version = req.version
    if not isinstance(version, int) or isinstance(version, bool):
        raise HTTPException(status_code=422, detail="version 必填且为整数")
    result = await asyncio.to_thread(
        services.settings.rollback, version, user_id)
    services.session.invalidate_agents()
    return result


@router.post("", response_model=SettingsPatchResponse)
async def settings_set(
    req: SettingsPatchRequest,
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """写入一批配置补丁（路径级），返回新版本号。"""
    result = await asyncio.to_thread(
        services.settings.patch, req.model_dump(), user_id)
    services.session.invalidate_agents()
    return result
