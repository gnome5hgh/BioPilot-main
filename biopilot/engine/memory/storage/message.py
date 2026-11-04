"""bio_message 表操作：对话消息的落盘与查询（窗口回放与审计的数据源）。

本文件只有裸 SQL 函数，不含业务规则；surrogate 清洗等语义由
services/message_manager.py 持有。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from biopilot.common.core.constants import MessageRole
from biopilot.engine.llm.domain.dto import response_meta_to_dict
from biopilot.engine.memory.storage.database import MemoryDB
from biopilot.engine.memory.schemas.stored_message import StoredMessage

__all__ = ["insert_message", "select_messages_by_agent", "select_messages_by_session",
           "select_messages_by_ids", "count_messages"]


def _now() -> str:
    """当前 UTC 时间转 ISO 字符串（统一时间戳格式）。"""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    """把一行查询结果拷成独立 dict（DictCursor 行本身就是 dict，这里防御性拷贝）。

    Args:
        row: dict，一行查询结果（列名可访问）

    Returns:
        该行的普通 dict（按列名取值）。
    """
    return dict(row)


def insert_message(db: MemoryDB, agent_id: str, m: StoredMessage,
                   user_id: str | None = None) -> None:
    """插入一条消息行：content 只存字符串（list/dict 内容序列化为 JSON），
    tool_calls / meta 序列化为 JSON，created_at 缺省取当前时间。

    Args:
        db: 数据库连接。
        agent_id: 消息所属 agent 标识。
        m: 持久化消息对象（已含 id, role, content 等字段）。

    边界与注意：
        - content 字段在 schema 中为 TEXT，落盘时必须为字符串或 None。
          若 m.content 是 list 或 dict（如多模态内容），则序列化为 JSON 字符串存储；
          否则直接存储原字符串（或 None）。
        - tool_calls 始终序列化为 JSON 数组字符串（即使为空列表）。
        - meta 为 None（非 assistant 消息、或端点未回信封）时存 NULL——「没有信封」
          与「信封里字段为 None」在库里都是可区分的（后者是一行 JSON）。
        - created_at 若未显式设置，则使用当前 UTC 时间。
    """
    db.execute(
        "INSERT INTO bio_message (id, agent_id, user_id, session_id, role, content, tool_calls,"
        " tool_call_id, step_id, run_id, otid, meta, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        # user_id=None（测试预置等直接调用）按列默认值 'local' 归一；
        # 引擎链路（ContextWindow）恒传真实归属。
        (m.id, agent_id, user_id or "local", m.session_id, m.role.value,
         # 若 content 是 list/dict，转为 JSON 字符串；否则原样保留
         json.dumps(m.content, ensure_ascii=False)
         if isinstance(m.content, (list, dict)) else m.content,
         json.dumps(m.tool_calls, ensure_ascii=False),
         m.tool_call_id, m.step_id, m.run_id, m.otid,
         json.dumps(response_meta_to_dict(m.meta), ensure_ascii=False)
         if m.meta is not None else None,
         m.created_at.isoformat() if m.created_at else _now()))


def select_messages_by_agent(db: MemoryDB, agent_id: str,
                             limit: int | None = None) -> list[dict]:
    """按 agent 取消息，按 created_at 升序（同刻用 seq 保插入序）；limit 可选。

    Args:
        db: 数据库连接。
        agent_id: 目标 agent 标识。
        limit: 可选返回条数上限，None 表示全部。

    Returns:
        消息行 dict 列表，按时间升序排列。

    排序细节：
        - 主排序 created_at（字符串 ISO 时间可字典序比较）。
        - 辅助排序 seq（自增插入序）确保同一时刻消息顺序稳定。
    """
    sql = "SELECT * FROM bio_message WHERE agent_id=? ORDER BY created_at, seq"
    params: list = [agent_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    cur = db.execute(sql, tuple(params))
    return [_row_to_dict(r) for r in cur.fetchall()]


def select_messages_by_ids(db: MemoryDB, ids: list[str]) -> list[dict]:
    """按 id 列表取消息，并保证返回顺序与输入 ids 一致。

    WHERE id IN (...) 返回行序任意；按输入 ids 建索引重排——压缩后按
    AgentState.message_ids 回放 in-context 窗口时对话顺序才正确。

    Args:
        db: 数据库连接。
        ids: 消息 id 列表（按期望顺序）。

    Returns:
        消息行 dict 列表，顺序与 ids 输入一致。

    注意：
        - 若 ids 为空，直接返回空列表，避免无效 SQL。
        - 使用字典 order 构建 id -> 索引映射，然后排序。
        - 若某个 id 不在表中，对应行缺失，排序时 `order.get(r["id"], 0)` 会将其放在开头，
          但这种情况通常不应发生（调用方应保证 ids 均有效）。
    """
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    cur = db.execute(f"SELECT * FROM bio_message WHERE id IN ({placeholders})", tuple(ids))
    rows = [dict(r) for r in cur.fetchall()]
    # 构建 id 到索引位置的映射
    order = {i: idx for idx, i in enumerate(ids)}
    # 按映射排序，若 id 缺失则排在前面（理论上不会发生）
    rows.sort(key=lambda r: order.get(r["id"], 0))
    return rows


def select_messages_by_session(db: MemoryDB, session_id: str,
                               limit: int | None = None) -> list[dict]:
    """按会话分组取消息（覆盖 supervisor 与子 agent），按时间升序。

    Args:
        db: 数据库连接。
        session_id: 会话标识。
        limit: 可选返回条数上限。

    Returns:
        消息行 dict 列表，按 created_at、seq 升序。
    """
    sql = ("SELECT * FROM bio_message WHERE COALESCE(session_id, agent_id)=?"
           " ORDER BY created_at, seq")
    params: list = [session_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(r) for r in db.execute(sql, tuple(params)).fetchall()]


def count_messages(db: MemoryDB, agent_id: str) -> int:
    """返回该 agent 的消息总数（MemoryConsolidator 游标与 size() 的数据源）。

    Args:
        db: 数据库连接。
        agent_id: agent 标识。

    Returns:
        消息总条数（包括所有历史消息，即使已被压缩移出窗口，因为物理行未删除）。
    """
    cur = db.execute("SELECT COUNT(*) AS c FROM bio_message WHERE agent_id=?", (agent_id,))
    return cur.fetchone()["c"]