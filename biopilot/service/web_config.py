"""Web 适配层配置（内网端口 / DSN）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebConfig:
    """Web 适配层配置（内网端口 / DSN）。

    Attributes:
        host: 监听地址——只允许回环/内网（信任边界的物理前提）。
        port: 监听端口。
        memory_dsn: 记忆库连接串（传给会话装配）。
        confirm_timeout_seconds: 确认等待上限（秒）；超时视为拒绝。
    """

    host: str = "127.0.0.1"
    port: int = 8300
    memory_dsn: str | None = None
    confirm_timeout_seconds: float = 300.0
