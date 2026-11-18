"""MessageManager：完整对话落盘与按会话读取。

本类实现 ``MessageStore`` 端口（agent 循环与窗口的消费面）：窗口选择策略
（message_ids 优先、降级全量）在这里持有；wire 消息 → StoredMessage 的翻译
与 surrogate 清洗在 ``MySqlMessageRepository``（适配层）。
"""
from __future__ import annotations

import logging

from biopilot.engine.memory.domain.ports import AgentStateStore, MessageRepository
from biopilot.engine.memory.domain.schemas.stored_message import StoredMessage

__all__ = ["MessageManager"]

logger = logging.getLogger(__name__)


class MessageManager:
    """对话消息的落盘与查询单点：窗口选择策略 + 委托存储端口。

    Attributes:
        messages: MessageRepository，bio_message 的存储端口
        agent_state: AgentStateStore | None，读 AgentState.message_ids 确定
            in-context 窗口；None 时降级为全量回放
    """

    def __init__(self, messages: MessageRepository,
                 agent_state: AgentStateStore | None = None):
        """初始化消息管理器。

        Args:
            messages: 消息存储端口（MySqlMessageRepository 或测试假件）。
            agent_state: 可选的会话状态端口（AgentManager），用于读取
                AgentState.message_ids 以确定 in-context 窗口。
        """
        self.messages = messages
        self.agent_state = agent_state

    def add_message(self, agent_id: str, wire,
                    session_id: str | None = None,
                    user_id: str = "") -> StoredMessage:
        """落盘一条消息并返回持久化版本（全部消息持久化的唯一漏斗）。

        信任边界：翻译与 surrogate 清洗在仓储适配器内完成——落盘的消息来自多个
        来源（用户输入、工具结果、合成消息、模型自由文本），add_message 是它们
        共同必经的单点。

        Args:
            agent_id: 所属 agent 标识（具体对话）。
            wire: LLM 层的原始消息。
            session_id: 会话分组标识；None 时回退为 agent_id（旧行为）。
            user_id: 归属用户（必填；引擎链路恒传真实归属）。

        Raises:
            ValueError: user_id 为空——引擎没有无用户的运行形态。

        Returns:
            持久化后的 StoredMessage 对象（含生成的 id 和 created_at）。
        """
        return self.messages.append(agent_id, wire, session_id, user_id)

    def get_messages_by_agent_id(self, agent_id: str,
                                 limit: int | None = None) -> list[StoredMessage]:
        """按 agent 取全部消息（升序）；limit 可选。

        Args:
            agent_id: agent 标识。
            limit: 最多返回条数（None 表示全部）。

        Returns:
            StoredMessage 列表，按 created_at 升序排列（同刻按 seq 排序保证插入顺序）。
        """
        return self.messages.by_agent(agent_id, limit=limit)

    def get_in_context_messages(self, agent_id: str,
                                limit: int | None = None) -> list[StoredMessage]:
        """回放该 agent 的 in-context 消息（AgentState.message_ids 指定的窗口）。

        有 agent_state 且 message_ids 非空时按 id 返回（压缩后的窗口：摘要 + 保留
        尾部）；message_ids 为空（首轮/未压缩）返回全部持久化消息——兼容。被驱逐的
        旧消息只移出窗口，不删 SQL 行（历史仍留在库中供审计/排障）。

        Args:
            agent_id: agent 标识。
            limit: 若降级到全部消息查询时，可选的条数限制（当 message_ids 存在时忽略）。

        Returns:
            StoredMessage 列表，顺序与 message_ids 一致（若使用窗口），或按时间升序（降级模式）。

        降级策略：
            - 优先从 AgentState.message_ids 取消息（已压缩的窗口）。
            - 若 message_ids 为空或 agent_state 不存在，回退到 get_messages_by_agent_id。
        """
        if self.agent_state is not None:
            try:
                state = self.agent_state.get_agent(agent_id)
                ids = state.message_ids
            except KeyError:
                ids = []
            # 若 message_ids 非空，则按 id 列表查询并保持顺序
            if ids:
                return self.messages.by_ids(ids)
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
        return self.messages.by_session(session_id, limit=limit)

    def size(self, agent_id: str) -> int:
        """返回该 agent 已落盘消息总数（MemoryConsolidator 游标与进度判断的数据源）。

        Args:
            agent_id: agent 标识。

        Returns:
            消息总数（所有历史，包括已压缩驱逐的消息，因为 SQL 行永不物理删除）。
        """
        return self.messages.count(agent_id)

    def list_user_messages_for_agent(self, agent_id: str) -> list[StoredMessage]:
        """返回该 agent 的全部 user 消息（供需要「只看用户说了什么」的场景）。

        Args:
            agent_id: agent 标识。

        Returns:
            仅包含 role="user" 的消息列表（按时间升序）。
        """
        return self.messages.user_messages(agent_id)
