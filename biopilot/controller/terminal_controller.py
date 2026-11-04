"""终端面板端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket

from biopilot.api.deps import get_services, require_user
from biopilot.schema.terminal import TerminalConfigResponse, TerminalRestartResponse
from biopilot.service.container import ServiceContainer

router = APIRouter(prefix="/terminal", tags=["terminal"])
ws_router = APIRouter(tags=["terminal"])


@router.get("/config", response_model=TerminalConfigResponse)
async def terminal_config(
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """返回当前部署是否启用宿主终端。"""
    return services.terminal.config()


@router.post("/restart", response_model=TerminalRestartResponse)
async def terminal_restart(
    user_id: str = Depends(require_user),
    services: ServiceContainer = Depends(get_services),
) -> dict:
    """结束该用户当前的 shell；下一次打开面板会启动新进程。"""
    return await services.terminal.restart(user_id)


@ws_router.websocket("/ws/terminal")
async def ws_terminal(ws: WebSocket) -> None:
    """终端 WebSocket：附着到该用户的持久 shell。"""
    await ws.app.state.services.terminal.run_websocket(ws)
