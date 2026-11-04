"""定时任务执行实现：与网页对话同一装配路径、同一全局并发闸。"""
from __future__ import annotations

import asyncio
import logging

from biopilot.domain.runtime_state import RuntimeState
from biopilot.service import state
from biopilot.service.errors import RequestValidationError
from biopilot.service.schedule_service import ScheduleService

logger = logging.getLogger(__name__)


async def _execute_scheduled(user_id: str, conversation_id: str, task: str,
                             key: str, agent_factory, gate) -> None:
    """执行一次定时任务（保留旧模块级入口，测试可直接 await）。

    Args:
        user_id: 归属用户。
        conversation_id: 归属会话。
        task: 任务文本（调用方已加「【定时任务】」前缀）。
        key: 进程内去重键（task_id）。
        agent_factory: 会话工厂（与对话同一路径）。
        gate: asyncio.Semaphore，全局并发闸。
    """
    try:
        async with gate:
            built = agent_factory(user_id, conversation_id)
            agent = await built if asyncio.iscoroutine(built) else built
            await agent.run(task)
    except Exception:
        logger.warning("定时任务执行失败（%s）", key, exc_info=True)
    finally:
        state._sched_running.discard(key)


class ScheduleServiceImpl(ScheduleService):
    """接收 Java 调度器投递并执行一轮 agent。"""

    def __init__(self, runtime: RuntimeState, agent_factory):
        self._runtime = runtime
        self._agent_factory = agent_factory

    def run(self, user_id: str, task_id: str, conversation_id: str,
            task: str) -> dict:
        """去重后后台执行一轮定时任务，HTTP 立即返回。"""
        conversation_id = str(conversation_id or "")
        task = str(task or "")
        task_id = str(task_id or "")
        if not conversation_id or not task:
            raise RequestValidationError("conversation_id 与 task 必填")
        key = task_id or f"{user_id}:{conversation_id}:{task[:32]}"
        if key in state._sched_running:
            return {"status": "skipped"}
        state._sched_running.add(key)
        asyncio.get_running_loop().create_task(self.execute(
            user_id, conversation_id, "【定时任务】" + task, key))
        return {"status": "accepted"}

    async def execute(self, user_id: str, conversation_id: str, task: str,
                      key: str) -> None:
        """执行一次定时任务。"""
        await _execute_scheduled(
            user_id, conversation_id, task, key,
            self._agent_factory, self._runtime.llm_gate)
