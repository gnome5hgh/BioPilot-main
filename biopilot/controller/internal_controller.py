"""Java ↔ Python 内部调用端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from biopilot.api.deps import get_services, require_internal
from biopilot.schema.internal import (
    KbRuntimeResponse,
    KbSyncRequest,
    KbSyncResponse,
    MarkDeletingResponse,
    PurgeResponse,
    ScheduleRunRequest,
    ScheduleRunResponse,
)
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/users/{target_id}/mark-deleting",
             response_model=MarkDeletingResponse)
async def mark_deleting(
    target_id: str,
    user_id: str = Depends(require_internal),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """删户第一阶段：标记归属。"""
    return services.user.mark_deleting(target_id)


@router.post("/users/{target_id}/purge", response_model=PurgeResponse)
async def purge_user(
    target_id: str,
    user_id: str = Depends(require_internal),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """物理清除该用户的全部引擎数据（幂等）。"""
    return services.user.purge(target_id)


@router.post("/kb/sync", response_model=KbSyncResponse)
async def internal_kb_sync(
    req: KbSyncRequest | None = None,
    user_id: str = Depends(require_internal),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """唤醒该用户的知识库索引。"""
    return services.kb.sync(user_id)


@router.get("/kb/runtime", response_model=KbRuntimeResponse)
async def internal_kb_runtime(
    user_id: str = Depends(require_internal),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """知识库运行时信息，供 Java 概览合并。"""
    return services.kb.runtime(user_id)


@router.post("/schedule/run", response_model=ScheduleRunResponse)
async def internal_schedule_run(
    req: ScheduleRunRequest,
    user_id: str = Depends(require_internal),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """Java 调度器投递到期任务：立即返回，后台跑一轮 agent。"""
    return services.schedule.run(
        user_id, req.task_id, req.conversation_id, req.task)
