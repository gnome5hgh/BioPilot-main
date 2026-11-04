"""知识库索引、对账与检索服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class KbService(ABC):
    """知识库运行时编排：索引、对账、试检索与分块读取。"""

    @abstractmethod
    def schedule_user_index(self, user_id: str) -> None:
        """在事件循环里后台触发一次索引。"""

    @abstractmethod
    def index_user_kb_sync(self, user_id: str) -> dict:
        """同步执行一轮该用户的索引。"""

    @abstractmethod
    async def reindex(self, user_id: str, force: bool) -> dict:
        """触发重建。"""

    @abstractmethod
    async def search(self, user_id: str, query: str, top_k) -> dict:
        """试检索。"""

    @abstractmethod
    async def chunks(self, user_id: str, paper_id: str) -> dict:
        """读取一篇论文的分块。"""

    @abstractmethod
    def sync(self, user_id: str) -> dict:
        """唤醒索引。"""

    @abstractmethod
    def runtime(self, user_id: str) -> dict:
        """返回引擎侧知识库运行时信息。"""

    @abstractmethod
    async def reconcile_loop(self) -> None:
        """周期对账循环。"""

    @abstractmethod
    def users_with_kb(self) -> list[str]:
        """列出知识库里还有勾选论文的用户。"""

    @abstractmethod
    def users_needing_reconcile(self) -> list[str]:
        """列出知识库派生状态不自洽的用户。"""
