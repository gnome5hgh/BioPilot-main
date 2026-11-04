"""Web 会话装配服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from biopilot.domain.web_session import WebSession


class AssemblyService(ABC):
    """按用户与会话装配 supervisor。"""

    @abstractmethod
    async def assemble(self, user_id: str, conversation_id: str,
                       config=None, confirm_callback=None,
                       project_id: str | None = None,
                       model_name: str | None = None) -> WebSession:
        """装配一次 Web 会话。"""

    @abstractmethod
    async def default_agent_factory(self, user_id: str, conversation_id: str,
                                    confirm_callback=None,
                                    project_id: str | None = None):
        """真实 agent 工厂：装配会话并登记整合队列。"""
