"""Java 平台内部端点客户端的共享入口（转发到按端点键的进程级缓存）。"""
from __future__ import annotations


def shared_platform_client():
    """返回共享的平台内部客户端（键含地址与 token，配置变更不吃陈旧值）。"""
    from biopilot.common.platform import shared_platform_client as _shared
    from biopilot.config import BioPilotConfig
    return _shared(BioPilotConfig.from_env())
