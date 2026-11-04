"""健康检查端点。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """返回进程存活状态。"""
    return {"status": "ok"}
