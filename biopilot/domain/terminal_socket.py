"""终端面板需要的最小 WebSocket 协议。

服务层只依赖这个协议，不直接依赖 FastAPI 的 ``WebSocket`` 类型。
"""
from __future__ import annotations

from typing import Any, Protocol


class TerminalSocket(Protocol):
    """WebSocket 的最小传输面：握手、关闭、收发文本帧。"""

    headers: Any

    async def accept(self) -> None:
        """接受握手。"""
        ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        """关闭连接。"""
        ...

    async def receive_text(self) -> str:
        """接收一条文本帧。"""
        ...

    async def send_text(self, data: str) -> None:
        """发送一条文本帧。"""
        ...
