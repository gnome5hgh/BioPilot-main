"""FastAPI 依赖：身份头校验与服务容器读取。"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request

from biopilot.common.utils.env import os_env
from biopilot.domain.runtime_state import RuntimeState
from biopilot.service.container import ServiceContainer


def require_user(
    x_user_id: str | None = Header(default=None),
) -> str:
    """用户态端点统一要求 X-User-Id（fail-closed）。"""
    if not x_user_id:
        raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
    return x_user_id


def require_internal(
    x_user_id: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None),
) -> str:
    """内部端点校验：token（配置了才校验）+ 归属用户。"""
    expected = os_env("BIOPILOT_INTERNAL_TOKEN", "") or ""
    if expected and x_internal_token != expected:
        raise HTTPException(status_code=403, detail="内部调用 token 无效")
    if not x_user_id:
        raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
    return x_user_id


def get_services(request: Request) -> ServiceContainer:
    """取出当前应用实例的服务容器。"""
    return request.app.state.services


def get_runtime(request: Request) -> RuntimeState:
    """取出当前应用实例的运行时状态。"""
    return request.app.state.runtime
