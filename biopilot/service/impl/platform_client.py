"""Java 平台内部端点客户端的进程级单例。"""
from __future__ import annotations

_platform_instance = None


def shared_platform_client():
    """返回进程级共享的平台内部客户端（懒建单例）。"""
    global _platform_instance
    if _platform_instance is None:
        from biopilot.common.platform import make_platform_client
        from biopilot.config import BioPilotConfig
        _platform_instance = make_platform_client(BioPilotConfig.from_env())
    return _platform_instance
