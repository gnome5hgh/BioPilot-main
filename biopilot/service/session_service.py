"""会话历史、删除与上下文用量服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SessionService(ABC):
    """会话级轻量查询与进程内缓存维护。"""

    @abstractmethod
    async def autotitle(self, user_id: str, conversation_id: str, task: str) -> None:
        """首条任务生成会话标题。"""

    @abstractmethod
    def history(self, user_id: str, conversation_id: str) -> dict:
        """取一段会话的可见历史。"""

    @abstractmethod
    def delete(self, user_id: str, conversation_id: str) -> dict:
        """删除一个会话及其进程内缓存。"""

    @abstractmethod
    def context_usage(self, user_id: str, conversation_id: str) -> dict:
        """当前会话的上下文窗口用量。"""

    @abstractmethod
    def invalidate_agents(self) -> None:
        """丢弃全部缓存的 Agent（设置保存后调用）。"""

    @abstractmethod
    def purge_runtime_for_user(self, target_id: str) -> None:
        """删户后丢弃该用户的进程内缓存。"""
