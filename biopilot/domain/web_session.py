"""Web 会话装配产物。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebSession:
    """web 会话装配产物（适配层持有：run 用 Agent，收尾用整合队列）。

    Attributes:
        agent: 装配完成的 supervisor。
        consolidation_queue: 每轮收尾的整合队列（跑在适配层事件循环上）。
    """

    agent: object
    consolidation_queue: object
