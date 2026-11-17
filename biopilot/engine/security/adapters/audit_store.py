"""bio_security_audit_event 表的 SQL 访问（适配层）。

AuditMiddleware（应用层）负责事件组装、span 树与「审计失败不毁主流程」的降级
语义；本模块只做「AuditEntry 载荷 ⇄ SQL 行」的翻译：insert-only 写入与按插入序
读回。表经 MemoryDB 的 _SCHEMA 幂等建表。
"""
from __future__ import annotations

from datetime import datetime

__all__ = ["insert_event", "read_payloads"]


def insert_event(db, payload: str, data: dict) -> None:
    """把一条审计事件 insert-only 写入 MySQL 审计表。

    多进程并发插入天然安全（无共享文件句柄，无需写锁）。payload 列存完整
    to_json_dict（固定键集，取证原文），核心列单提出来供管理端按维度查询。

    Args:
        db: MemoryDB，连接池。
        payload: 已清洗的完整载荷 JSON 字符串。
        data: 载荷 dict（核心列从中单提）。
    """
    db.execute(
        "INSERT INTO bio_security_audit_event (user_id, event_type, span_id, trace_id,"
        " session_id, agent_type, tool_name, risk_level, turn, started_at,"
        " ended_at, policy_decision, result_status, approval_outcome,"
        " created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data.get("user_id"), data.get("event_type"), data.get("span_id"),
         data.get("trace_id"), data.get("session_id"),
         data.get("agent_type"), data.get("tool_name"),
         data.get("risk_level"), data.get("turn"), data.get("started_at"),
         data.get("ended_at"), data.get("policy_decision"),
         data.get("result_status"), data.get("approval_outcome"),
         datetime.now().isoformat(), payload))


def read_payloads(db) -> list[dict]:
    """按插入序读回全部审计事件的载荷 dict。

    供测试断言与管理端查询使用；生产侧按维度查询走 SQL 直接过滤核心列。

    Args:
        db: MemoryDB。

    Returns:
        事件 dict 列表（键为标准审计字段名），按插入顺序。
    """
    import json

    rows = db.execute(
        "SELECT payload FROM bio_security_audit_event ORDER BY id").fetchall()
    return [json.loads(r["payload"]) for r in rows]
