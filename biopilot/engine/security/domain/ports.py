"""security 域的端口定义（领域层）：审计事件的写入与读回契约。

审计真相源是 ``bio_security_audit_event`` 表（MySQL）；审计中间件只依赖本端口，
MySQL 实现在 adapters，测试传内存假件即可。
"""
from typing import Protocol

__all__ = ["AuditSink"]


class AuditSink(Protocol):
    """审计事件的 insert-only 写入与按插入序读回。"""

    def write(self, payload: str, data: dict) -> None:
        """写入一条审计事件（payload 为完整取证 JSON；data 为核心列拆解）。

        Args:
            payload: 全量取证 JSON 字符串（固定键集）。
            data: 核心列拆解（event_type/span_id/trace_id/...）。
        """
        ...

    def read_all(self) -> list[dict]:
        """按插入序读回全部审计事件（payload 还原为 dict 形态）。"""
        ...
