"""汇总全部 APIRouter。"""
from __future__ import annotations

from fastapi import APIRouter

from biopilot.controller import (
    chat_controller,
    health_controller,
    internal_controller,
    kb_controller,
    model_controller,
    session_controller,
    settings_controller,
    terminal_controller,
)

api_router = APIRouter()
api_router.include_router(health_controller.router)
api_router.include_router(chat_controller.router)
api_router.include_router(session_controller.router)
api_router.include_router(settings_controller.router)
api_router.include_router(model_controller.router)
api_router.include_router(terminal_controller.router)
api_router.include_router(terminal_controller.ws_router)
api_router.include_router(kb_controller.router)
api_router.include_router(internal_controller.router)
