"""网页终端服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from biopilot.domain.terminal_socket import TerminalSocket


class TerminalService(ABC):
    """按用户复用的宿主 shell 会话。"""

    @abstractmethod
    def config(self) -> dict:
        """返回终端开关与 shell 名。"""

    @abstractmethod
    async def restart(self, user_id: str) -> dict:
        """结束该用户当前 shell。"""

    @abstractmethod
    async def run_websocket(self, ws: TerminalSocket) -> None:
        """处理一条终端 WebSocket 连接。"""

    @abstractmethod
    async def reaper(self) -> None:
        """后台回收空闲 shell。"""

    @abstractmethod
    async def shutdown(self) -> None:
        """停服时结束所有 shell。"""
