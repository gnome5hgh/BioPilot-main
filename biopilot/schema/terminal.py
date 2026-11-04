"""终端面板 HTTP 契约。"""
from __future__ import annotations

from pydantic import BaseModel


class TerminalConfigResponse(BaseModel):
    """``GET /terminal/config`` 的响应。"""

    enabled: bool
    shell: str


class TerminalRestartResponse(BaseModel):
    """``POST /terminal/restart`` 的响应。"""

    status: str
