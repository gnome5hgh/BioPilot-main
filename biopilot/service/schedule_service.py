"""定时任务执行服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ScheduleService(ABC):
    """接收 Java 调度器投递并执行一轮 agent。"""

    @abstractmethod
    def run(self, user_id: str, task_id: str, conversation_id: str,
            task: str) -> dict:
        """去重后后台执行一轮定时任务。"""

    @abstractmethod
    async def execute(self, user_id: str, conversation_id: str, task: str,
                      key: str) -> None:
        """执行一次定时任务。"""
