"""记忆域的端口定义（领域层）：编排层消费记忆设施的契约。

对应三层架构方法论里 ``SessionStore`` 一族接口——Agent 循环与窗口只依赖本协议，
不依赖任何 manager 具体类；MessageManager / AgentManager / BlockManager（应用层
服务）按结构化类型天然满足，测试传内存假件即可。

端口面按真实消费收敛（Agent/ContextWindow 实际调用的方法）：
- ``MessageStore``：窗口落盘与跨轮回放
- ``AgentStateStore``：窗口 id 列表（AgentState.message_ids）的持久化
- ``MemoryBlockReader``：每轮重建记忆段时的块读取（只读；写归轮末整合器）
"""
from typing import Any, Protocol

from biopilot.engine.memory.domain.schemas.block import Block
from biopilot.engine.memory.domain.schemas.stored_message import StoredMessage

__all__ = ["MessageStore", "AgentStateStore", "MemoryBlockReader"]


class MessageStore(Protocol):
    """对话消息的落盘与按窗口回放契约。"""

    def add_message(self, agent_id: str, wire, session_id: str | None = None,
                    user_id: str = "") -> StoredMessage:
        """落盘一条消息并返回持久化版本（全部消息持久化的唯一漏斗）。

        Args:
            agent_id: 所属 agent 标识（具体对话）。
            wire: LLM 层的原始消息。
            session_id: 会话分组标识；None 时回退为 agent_id。
            user_id: 归属用户。

        Returns:
            StoredMessage：补齐 id/created_at 的持久化版本。
        """
        ...

    def get_in_context_messages(self, agent_id: str,
                               limit: int | None = None) -> list[StoredMessage]:
        """回放该 agent 的 in-context 消息（AgentState.message_ids 指定的窗口）。

        Args:
            agent_id: agent 标识。
            limit: 降级到全量查询时的条数限制（使用窗口时忽略）。

        Returns:
            StoredMessage 列表，顺序与窗口一致（或按时间升序的降级模式）。
        """
        ...


class AgentStateStore(Protocol):
    """会话状态（窗口 id 列表）的持久化契约。"""

    def update_agent(self, agent_id: str, **kwargs: Any):
        """局部更新 AgentState 白名单字段（list/dict 自动序列化 JSON）。

        Args:
            agent_id: 目标会话标识。
            **kwargs: 白名单字段（name/description/system/model/
                context_window_limit/message_ids）。

        Returns:
            更新后的 AgentState。
        """
        ...


class MemoryBlockReader(Protocol):
    """核心记忆块的只读契约（写侧归轮末整合器，不在本端口）。"""

    def list_blocks(self) -> list[Block]:
        """列出当前用户域的全部核心记忆块（按显示序）。

        Returns:
            Block 列表。
        """
        ...
