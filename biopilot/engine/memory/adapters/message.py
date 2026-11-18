"""bio_message 表操作：对话消息的落盘与查询（窗口回放与审计的数据源）。

裸 SQL 函数 + ``MySqlMessageRepository``（``MessageRepository`` 端口的 MySQL
实现）。wire 消息 → StoredMessage 的翻译与 surrogate 清洗在本文件完成——
「翻译」是适配层职责；业务规则（窗口选择策略）在 application/message_manager。
"""
from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import datetime, timezone

from biopilot.common.constants import MessageRole
from biopilot.common.utils.text import sanitize_surrogates
from biopilot.engine.llm.adapters.api import response_meta_from_dict, response_meta_to_dict
from biopilot.engine.memory.adapters.database import MemoryDB
from biopilot.engine.memory.domain.schemas.stored_message import StoredMessage

__all__ = ["insert_message", "select_messages_by_agent", "select_messages_by_session",
           "select_messages_by_ids", "count_messages", "row_to_schema"]


def row_to_schema(row: dict) -> StoredMessage:
    """把 DB 行转回 StoredMessage（tool_calls / meta 从 JSON 还原）。

    content 落盘恒为字符串（入库前只产出 str；schema content 为 str|None），直接
    原样回放即可——不能对以 {/[ 开头的字符串内容做 json.loads，否则会把它变成
    dict/list，StoredMessage.content 类型校验（str|None）直接抛 ValidationError。

    Args:
        row: 数据库行（dict 形式）。

    Returns:
        StoredMessage 实例。

    重要边界：
        - content 字段保持原样字符串，不做 JSON 解析（即使内容看起来像 JSON）。
        - tool_calls 字段是 JSON 数组字符串，需反序列化为 list。
        - meta 字段是信封 JSON 字符串；本列由增量迁移补出，旧行为 NULL。
    """
    return StoredMessage(
        id=row["id"], session_id=row.get("session_id") or row.get("agent_id"),
        user_id=row.get("user_id"),
        role=MessageRole(row["role"]), content=row["content"],
        tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else [],
        tool_call_id=row["tool_call_id"], step_id=row["step_id"],
        run_id=row["run_id"], otid=row["otid"], created_at=row["created_at"],
        meta=response_meta_from_dict(json.loads(row["meta"])) if row["meta"] else None,
    )


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
        user_id: 归属用户（必填；引擎链路恒传真实归属）。

    Raises:
        ValueError: user_id 为空——引擎没有无用户的运行形态。

    边界与注意：
        - content 字段在 schema 中为 TEXT，落盘时必须为字符串或 None。
          若 m.content 是 list 或 dict（如多模态内容），则序列化为 JSON 字符串存储；
          否则直接存储原字符串（或 None）。
        - tool_calls 始终序列化为 JSON 数组字符串（即使为空列表）。
        - meta 为 None（非 assistant 消息、或端点未回信封）时存 NULL——「没有信封」
          与「信封里字段为 None」在库里都是可区分的（后者是一行 JSON）。
        - created_at 若未显式设置，则使用当前 UTC 时间。
    """
    if not user_id:
        # 引擎没有无用户的运行形态，绝不静默落假归属；引擎链路恒传真实归属。
        raise ValueError("消息落盘缺少归属用户（user_id）")
    db.execute(
        "INSERT INTO bio_message (id, agent_id, user_id, session_id, role, content, tool_calls,"
        " tool_call_id, step_id, run_id, otid, meta, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (m.id, agent_id, user_id, m.session_id, m.role.value,
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

def first_user_content(db: MemoryDB, agent_id: str) -> str | None:
    """取该会话首条用户消息的 content（会话列表预览用）；无消息返回 None。

    Args:
        db: 数据库连接。
        agent_id: 会话标识。

    Returns:
        str | None：首条用户消息原文；该会话还没有消息时 None。
    """
    row = db.execute(
        "SELECT content FROM bio_message WHERE agent_id=? AND role='user'"
        " ORDER BY created_at, seq LIMIT 1", (agent_id,)).fetchone()
    return None if row is None else row["content"]


class MySqlMessageRepository:
    """``MessageRepository`` 的 MySQL 实现：wire 消息 → StoredMessage 的翻译、
    surrogate 清洗与落盘/查询。

    「翻译」属于适配层职责：wire 消息（llm 层）→ StoredMessage 的映射、信封
    清洗都在这里完成，应用层只见领域对象与原始行。
    """

    def __init__(self, db: MemoryDB):
        """绑定连接。

        Args:
            db: 数据库连接（需已初始化）。
        """
        self._db = db

    def append(self, agent_id: str, wire, session_id: str | None,
               user_id: str) -> StoredMessage:
        """清洗并落盘一条 wire 消息，返回持久化版本。

        清洗是全角色并集：content 与响应信封（思维链/拒答）一视同仁——
        bio_message 表严格 UTF-8，代理码点写入会炸（整条消息落盘失败）。
        replace 生成副本，不改调用方 wire。

        Args:
            agent_id: 所属 agent 标识。
            wire: LLM 层的原始消息。
            session_id: 会话分组标识；None 回退为 agent_id。
            user_id: 归属用户（必填）。

        Returns:
            StoredMessage：补齐 id/created_at 的持久化版本。
        """
        wire = replace(wire, content=sanitize_surrogates(wire.content))
        meta = getattr(wire, "meta", None)
        if meta is not None:
            meta = _sanitize_response_meta(meta)
            wire = replace(wire, meta=meta)
        m = _wire_to_schema(wire, session_id or agent_id)
        insert_message(self._db, agent_id, m, user_id=user_id)
        return m

    def by_agent(self, agent_id: str, limit: int | None = None) -> list[StoredMessage]:
        """按 agent 取全部消息（升序）；limit 可选。"""
        rows = select_messages_by_agent(self._db, agent_id, limit=limit)
        return [row_to_schema(r) for r in rows]

    def by_ids(self, ids: list[str]) -> list[StoredMessage]:
        """按 id 列表取消息，顺序与 ids 一致。"""
        rows = select_messages_by_ids(self._db, ids)
        return [row_to_schema(r) for r in rows]

    def by_session(self, session_id: str, limit: int | None = None) -> list[StoredMessage]:
        """按会话分组取消息（覆盖 supervisor 与子 agent）。"""
        rows = select_messages_by_session(self._db, session_id, limit=limit)
        return [row_to_schema(r) for r in rows]

    def count(self, agent_id: str) -> int:
        """该 agent 已落盘消息总数。"""
        return count_messages(self._db, agent_id)

    def user_messages(self, agent_id: str) -> list[StoredMessage]:
        """该 agent 的全部 user 消息（升序）。"""
        rows = select_messages_by_agent(self._db, agent_id)
        return [row_to_schema(r) for r in rows if r["role"] == "user"]

    def first_user_content(self, agent_id: str) -> str | None:
        """首条用户消息原文（会话列表预览）；无消息返回 None。"""
        return first_user_content(self._db, agent_id)


def _sanitize_response_meta(meta) -> object:
    """清洗信封里的文本字段（思维链与拒答是模型自由文本，同样可能带未配对代理）。

    Args:
        meta: 从端点响应派生的信封。

    Returns:
        文本字段已清洗的副本（数字字段原样）。
    """
    values = {f.name: getattr(meta, f.name) for f in fields(meta)}
    for name, value in values.items():
        if isinstance(value, str):
            values[name] = sanitize_surrogates(value)
    return replace(meta, **values)


def _wire_to_schema(wire, session_id: str | None = None) -> StoredMessage:
    """把 wire 消息转成 StoredMessage：补 role 枚举 / 空 tool_calls / 时间戳。

    持久化是全角色的**并集**：表里 tool_calls / tool_call_id / meta 每一行都有列，
    非本角色的行存空值。故这里按属性取（wire 侧这些字段只存在于 assistant / tool
    子类上），取不到即归一为空。meta 是被落盘的响应信封（token 用量/结束原因等）。

    Args:
        wire: LLM 层的原始消息（各角色子类之一）。
        session_id: 会话分组标识；None 时由调用方回退为 agent_id。

    Returns:
        StoredMessage 对象，自动填充当前 UTC 时间作为 created_at。
    """
    return StoredMessage(
        session_id=session_id,
        role=MessageRole(wire.role),
        content=wire.content,
        tool_calls=getattr(wire, "tool_calls", None) or [],  # 确保为列表，避免 None
        tool_call_id=getattr(wire, "tool_call_id", None),
        meta=getattr(wire, "meta", None),
        created_at=datetime.now(timezone.utc),
    )
