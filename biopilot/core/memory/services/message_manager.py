"""MessageManager：完整对话落盘与按会话读取。

wire 消息（`biopilot.core.llm` 的 Message）→ StoredMessage（补 id/created_at）→
bio_message 表。add_message 是全部消息持久化的唯一漏斗：在此清洗 surrogateescape
残留（content 与响应信封里的思维链/拒答一视同仁）。本层不做会话检索——跨会话知识
只走记忆块，历史消息仅供窗口回放与审计/排障。
"""
from __future__ import annotations

import logging
from dataclasses import fields, replace
from datetime import datetime, timezone

from biopilot.core.llm import Message, ResponseMeta, response_meta_from_dict
from biopilot.common.core.constants import MessageRole
from biopilot.core.memory.storage import message as message_orm
from biopilot.core.memory.storage.database import MemoryDB
from biopilot.core.memory.schemas.stored_message import StoredMessage
from biopilot.common.core.utils.text import sanitize_surrogates

__all__ = ["MessageManager"]

logger = logging.getLogger(__name__)


def _sanitize_response_meta(meta: ResponseMeta) -> ResponseMeta:
    """清洗信封里的文本字段（思维链与拒答是模型自由文本，同样可能带未配对代理）。

    bio_message 表严格 UTF-8，代理码点写入会炸——信封与 content 进同一张表，故共用同一道
    清洗。不清的后果不是丢一个字符，而是整条消息落盘失败（INSERT 抛 UnicodeEncodeError）。

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


def _wire_to_schema(wire: Message, session_id: str | None = None) -> StoredMessage:
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


def _row_to_schema(row: dict) -> StoredMessage:
    """把 DB 行转回 StoredMessage（tool_calls / meta 从 JSON 还原）。

    content 落盘恒为字符串（_wire_to_schema 只产出 str；schema content 为
    str|None），直接原样回放即可——不能对以 {/[ 开头的字符串内容做 json.loads，
    否则会把它变成 dict/list，StoredMessage.content 类型校验（str|None）直接抛
    ValidationError。

    Args:
        row: 数据库行（dict 形式）。

    Returns:
        StoredMessage 实例。

    重要边界：
        - content 字段保持原样字符串，不做 JSON 解析（即使内容看起来像 JSON）。
        - tool_calls 字段是 JSON 数组字符串，需反序列化为 list。
        - meta 字段是信封 JSON 字符串；本列由增量迁移补出，旧行为 NULL。
    """
    import json
    return StoredMessage(
        id=row["id"], session_id=row.get("session_id") or row.get("agent_id"),
        user_id=row.get("user_id"),
        role=MessageRole(row["role"]), content=row["content"],
        tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else [],
        tool_call_id=row["tool_call_id"], step_id=row["step_id"],
        run_id=row["run_id"], otid=row["otid"], created_at=row["created_at"],
        meta=response_meta_from_dict(json.loads(row["meta"])) if row["meta"] else None,
    )


class MessageManager:
    """对话消息的落盘与查询单点：负责清洗、记录与 in-context 回放。

    Attributes:
        db: MemoryDB，bio_message 表的连接
        agent_manager: AgentManager | None，用于读取 AgentState.message_ids 确定 in-context 窗口
    """

    def __init__(self, db: MemoryDB, agent_manager=None):
        """初始化消息管理器。

        Args:
            db: 数据库连接。
            agent_manager: 可选的 AgentManager 实例，用于读取 AgentState.message_ids
                以确定 in-context 窗口。
        """
        self.db = db
        self.agent_manager = agent_manager  # 可选：读 AgentState.message_ids（in-context 窗口）

    def add_message(self, agent_id: str, wire: Message,
                    session_id: str | None = None,
                    user_id: str | None = None) -> StoredMessage:
        """落盘一条消息并返回持久化版本（全部消息持久化的唯一漏斗）。

        信任边界：清洗代理码点（surrogateescape 残留）——bio_message 表严格 UTF-8
        写入，代理会炸。落盘的消息来自多个来源（用户输入、工具结果、合成消息、模型
        自由文本），add_message 是它们共同必经的单点，在此堵漏最稳（replace 生成
        副本，不改调用方 wire）。信封里的思维链与拒答同样是模型自由文本，走同一道清洗。

        Args:
            agent_id: 所属 agent 标识（具体对话）。
            wire: LLM 层的原始消息。
            session_id: 会话分组标识；None 时回退为 agent_id（旧行为）。
            user_id: 归属用户（行级隔离列）；引擎链路（ContextWindow）恒传，
                直接调用方（测试预置等）缺省为 NULL。

        Returns:
            持久化后的 StoredMessage 对象（含生成的 id 和 created_at）。

        注意：
            - 使用 dataclasses.replace 生成新对象，不修改原 wire。
            - 清洗函数 sanitize_surrogates 将无效代理码点替换为 �，确保数据库写入安全。
        """
        # 清洗 content 中的 surrogateescape 残留（防止写入数据库时 UnicodeEncodeError）
        wire = replace(wire, content=sanitize_surrogates(wire.content))
        meta = getattr(wire, "meta", None)
        if meta is not None:
            wire = replace(wire, meta=_sanitize_response_meta(meta))
        m = _wire_to_schema(wire, session_id or agent_id)
        message_orm.insert_message(self.db, agent_id, m, user_id=user_id)
        return m

    def get_messages_by_agent_id(self, agent_id: str,
                                 limit: int | None = None) -> list[StoredMessage]:
        """按 agent 取全部消息（升序）；limit 可选。

        Args:
            agent_id: agent 标识。
            limit: 最多返回条数（None 表示全部）。

        Returns:
            StoredMessage 列表，按 created_at 升序排列（同刻按 seq 排序保证插入顺序）。
        """
        rows = message_orm.select_messages_by_agent(self.db, agent_id, limit=limit)
        return [_row_to_schema(r) for r in rows]

    def get_in_context_messages(self, agent_id: str,
                                limit: int | None = None) -> list[StoredMessage]:
        """回放该 agent 的 in-context 消息（AgentState.message_ids 指定的窗口）。

        有 agent_manager 且 message_ids 非空时按 id 返回（压缩后的窗口：摘要 + 保留
        尾部）；message_ids 为空（首轮/未压缩）返回全部持久化消息——兼容。被驱逐的
        旧消息只移出窗口，不删 SQL 行（历史仍留在库中供审计/排障）。

        Args:
            agent_id: agent 标识。
            limit: 若降级到全部消息查询时，可选的条数限制（当 message_ids 存在时忽略）。

        Returns:
            StoredMessage 列表，顺序与 message_ids 一致（若使用窗口），或按时间升序（降级模式）。

        降级策略：
            - 优先从 AgentState.message_ids 取消息（已压缩的窗口）。
            - 若 message_ids 为空或 AgentManager 不存在，回退到 get_messages_by_agent_id。
        """
        # 若提供了 agent_manager，尝试从 AgentState 读取 message_ids
        if self.agent_manager is not None:
            try:
                state = self.agent_manager.get_agent(agent_id)
                ids = state.message_ids
            except KeyError:
                ids = []
            # 若 message_ids 非空，则按 id 列表查询并保持顺序
            if ids:
                rows = message_orm.select_messages_by_ids(self.db, ids)
                return [_row_to_schema(r) for r in rows]
        # 降级：返回全部消息（首轮/未压缩场景）
        return self.get_messages_by_agent_id(agent_id, limit=limit)

    def get_messages_by_session(self, session_id: str,
                                limit: int | None = None) -> list[StoredMessage]:
        """按会话分组取消息（覆盖 supervisor 与子 agent）。

        Args:
            session_id: 会话标识。
            limit: 可选返回条数上限。

        Returns:
            StoredMessage 列表，按时间升序。
        """
        rows = message_orm.select_messages_by_session(
            self.db, session_id, limit=limit)
        return [_row_to_schema(r) for r in rows]

    def size(self, agent_id: str) -> int:
        """返回该 agent 已落盘消息总数（MemoryConsolidator 游标与进度判断的数据源）。

        Args:
            agent_id: agent 标识。

        Returns:
            消息总数（所有历史，包括已压缩驱逐的消息，因为 SQL 行永不物理删除）。
        """
        return message_orm.count_messages(self.db, agent_id)

    def list_user_messages_for_agent(self, agent_id: str) -> list[StoredMessage]:
        """返回该 agent 的全部 user 消息（供需要「只看用户说了什么」的场景）。

        Args:
            agent_id: agent 标识。

        Returns:
            仅包含 role="user" 的消息列表（按时间升序）。
        """
        rows = message_orm.select_messages_by_agent(self.db, agent_id)
        return [_row_to_schema(r) for r in rows if r["role"] == "user"]

