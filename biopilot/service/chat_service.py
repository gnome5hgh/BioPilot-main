"""对话流与确认服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable


class ChatService(ABC):
    """对话 SSE 流、确认往返与轮末整合收尾。"""

    @abstractmethod
    async def confirm(self, user_id: str, conversation_id: str, req_id: str,
                      approved: bool) -> dict:
        """结算一次确认请求。"""

    @abstractmethod
    def confirm_callback(self, user_id: str, conversation_id: str):
        """构造绑定会话的确认回调。"""

    @abstractmethod
    async def stream(self, user_id: str, task: str, conversation_id: str,
                     project_id: str | None, attachments: list[dict],
                     is_disconnected: Callable[[], Awaitable[bool]]
                     ) -> AsyncIterator[str]:
        """产出 SSE 帧（异步生成器）。"""

    @abstractmethod
    async def flush_consolidations(self) -> None:
        """停服时 flush 全部整合队列。"""
