"""每个 FastAPI 应用实例持有的运行时状态。

这里的字段与旧 ``create_app`` 的闭包变量一一对应：缓存、并发闸、确认 future
与活动流队列都按应用实例隔离；进程级共享状态在 ``biopilot.service.state``。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class RuntimeState:
    """应用实例级可变状态。"""

    agents: dict = field(default_factory=dict)
    llm_gate: asyncio.Semaphore | None = None
    user_runs: dict = field(default_factory=dict)
    agent_last_used: dict = field(default_factory=dict)
    usage_baseline: dict = field(default_factory=dict)
    pending_confirms: dict = field(default_factory=dict)
    active_queues: dict = field(default_factory=dict)

    @classmethod
    def create(cls, config) -> "RuntimeState":
        """按 Web 配置创建运行时状态（全局并发闸在这里初始化）。"""
        return cls(
            llm_gate=asyncio.Semaphore(
                getattr(config, "llm_max_concurrency", 8)),
        )
