"""记忆域的端口定义（领域层）：编排层消费记忆设施的契约。

两类端口：
- **消费面端口**（agent 循环与窗口依赖的能力）：``MessageStore`` /
  ``AgentStateStore`` / ``MemoryBlockReader``——由记忆应用服务满足，测试传内存
  假件即可。
- **存储端口**（本模块自己的外部世界）：``BlockRepository`` / ``MessageRepository``
  / ``AgentStateRepository`` / ``ConsolidationCursorStore``——实现全部住在
  ``adapters/``（MySQL），应用层只经端口访问，不得直接摸 SQL。

端口面按真实消费收敛（Agent/ContextWindow/Consolidator 实际调用的方法）。
"""
from typing import Any, Callable, Protocol

from biopilot.engine.memory.domain.schemas.agent import AgentState
from biopilot.engine.memory.domain.schemas.block import Block
from biopilot.engine.memory.domain.schemas.stored_message import StoredMessage

__all__ = [
    "MessageStore", "AgentStateStore", "MemoryBlockReader",
    "BlockRepository", "MessageRepository", "AgentStateRepository",
    "ConsolidationCursorStore", "RunMutex",
]


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

    def get_agent(self, agent_id: str) -> AgentState:
        """按 id 取 AgentState（不校验归属；窗口回放用）。

        Args:
            agent_id: 目标会话标识。

        Returns:
            当前 AgentState。

        Raises:
            KeyError: 会话不存在。
        """
        ...

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


class BlockRepository(Protocol):
    """核心块及其历史快照的存储契约（MySQL 实现，行级按 user_id 隔离）。

    不变式（read_only / limit）由应用层持有：``mutate`` 把「事务 + 行锁 + CAS
    重放」的存储机制收在适配器，业务校验由应用层传入的 mutator 抛领域错误。
    """

    def list_blocks(self) -> list[Block]:
        """列出该用户的全部块（按创建时间升序）。"""
        ...

    def get_by_label(self, label: str) -> Block | None:
        """按 label 取块（取首个命中）；不存在返回 None。"""
        ...

    def get_by_id(self, block_id: str) -> Block | None:
        """按 id 取块；不存在返回 None。"""
        ...

    def create(self, block: Block) -> None:
        """插入新块（初始版本号 1，metadata 序列化为 JSON）。"""
        ...

    def mutate(self, label: str,
               mutator: Callable[[Block], str | None]) -> Block | None:
        """一次持锁事务内读-改-写：FOR UPDATE 锁行 → mutator 算新值 → 快照 → CAS 写入。

        CAS 冲突（版本被并发推进）时在最新值上重放 mutator（要求 mutator 是
        纯函数）；连续冲突超过上限抛 ``ConcurrentUpdateError``。

        Args:
            label: 目标块标签。
            mutator: 接收当前 Block、返回新值的纯函数；返回 None 表示「判定不改」
                （不写、不推进版本）；read_only / limit 校验由 mutator 抛领域错误。

        Returns:
            更新后的 Block；mutator 返回 None 时为 None。

        Raises:
            KeyError: label 不存在。
            ConcurrentUpdateError: 重试后仍冲突。
        """
        ...

    def update_value(self, block_id: str, value: str,
                     expected_version: int) -> None:
        """CAS 写入原语（回滚路径用）：版本不匹配抛 ``ConcurrentUpdateError``。"""
        ...

    def update_label(self, block_id: str, label: str) -> None:
        """原地改写块 label（迁移专用；不动 value/version/updated_at）。"""
        ...

    def delete(self, block_id: str) -> None:
        """物理删除块行。"""
        ...

    def checkpoint(self, block: Block, version: int = 0) -> None:
        """把块当前状态快照进历史表；version 记录快照时刻的版本标注。"""
        ...

    def history(self, block_id: str) -> list[dict]:
        """按 id 升序返回该块的全部历史快照行（从旧到新）。"""
        ...

    def restore_snapshot(self, history_id: int) -> dict:
        """取指定历史快照行；不存在抛 ``KeyError``。"""
        ...


class MessageRepository(Protocol):
    """对话消息（bio_message）的存储契约：落盘、按窗口回放、审计查询。"""

    def append(self, agent_id: str, wire, session_id: str | None,
               user_id: str) -> StoredMessage:
        """落盘一条 wire 消息并返回持久化版本（翻译与清洗都在适配器）。

        Args:
            agent_id: 所属 agent 标识。
            wire: LLM 层的原始消息（四角色子类之一）。
            session_id: 会话分组标识；None 时回退为 agent_id。
            user_id: 归属用户（必填）。

        Returns:
            StoredMessage：补齐 id/created_at 的持久化版本。
        """
        ...

    def by_agent(self, agent_id: str, limit: int | None = None) -> list[StoredMessage]:
        """按 agent 取全部消息（升序）；limit 可选。"""
        ...

    def by_ids(self, ids: list[str]) -> list[StoredMessage]:
        """按 id 列表取消息，返回顺序与 ids 一致（压缩后窗口回放）。"""
        ...

    def by_session(self, session_id: str,
                   limit: int | None = None) -> list[StoredMessage]:
        """按会话分组取消息（覆盖 supervisor 与子 agent）。"""
        ...

    def count(self, agent_id: str) -> int:
        """该 agent 已落盘消息总数（含已被压缩移出窗口的历史行）。"""
        ...

    def user_messages(self, agent_id: str) -> list[StoredMessage]:
        """该 agent 的全部 user 消息（升序）。"""
        ...

    def first_user_content(self, agent_id: str) -> str | None:
        """首条用户消息原文（会话列表预览）；无消息返回 None。"""
        ...


class AgentStateRepository(Protocol):
    """会话状态行（bio_agent_state）的存储契约。"""

    def owner(self, agent_id: str) -> str | None:
        """读一行当前的归属 user_id；行不存在返回 None。"""
        ...

    def get(self, agent_id: str, user_id: str | None = None) -> AgentState | None:
        """按 id 取会话状态（可选归属过滤）；无匹配返回 None。

        Args:
            agent_id: 会话标识。
            user_id: 归属过滤（None 不过滤；传入则要求行归属该用户）。
        """
        ...

    def replace(self, agent_id: str, user_id: str, name: str | None,
                project_id: str | None) -> None:
        """REPLACE INTO 幂等写入一行（初始 message_ids 为空列表）。"""
        ...

    def update_fields(self, agent_id: str, updates: dict[str, str]) -> None:
        """按「列名 → 已序列化值」逐列更新一行（键来自应用层白名单）。"""
        ...

    def list_session_rows(self, user_id: str, limit: int,
                          project_id: str | None = None) -> list[dict]:
        """列出该用户的会话行（新→旧），可选项目过滤。"""
        ...

    def mark_user_deleting(self, target_id: str) -> None:
        """删户第一阶段：把归属改名为 deleting:<uid>，让新请求不再复用。"""
        ...

    def delete_conversation(self, user_id: str, conversation_id: str) -> int:
        """删除一个会话的状态行；返回删除行数。"""
        ...

    def delete_by_user(self, target_id: str) -> None:
        """删除该用户的全部状态行（含 mark-deleting 改名后的行）。"""
        ...


class ConsolidationCursorStore(Protocol):
    """整合消费权游标（bio_memory_consolidation_cursor）的存储契约。

    行存在即「该 agent 已消费到 cursor 条」；行不存在时由应用层按消息数回填。
    """

    def ensure(self, agent_id: str) -> None:
        """初始化游标行为 0（已有行保持不动）。"""
        ...

    def load(self, agent_id: str) -> int | None:
        """读当前游标；行不存在返回 None。"""
        ...

    def save(self, agent_id: str, cursor: int) -> None:
        """推进游标（REPLACE 幂等）。"""
        ...

    def delete_for_user(self, target_id: str) -> None:
        """按 agent_state 归属清理游标（游标表没有 user_id 列）。"""
        ...


class RunMutex(Protocol):
    """跨进程命名互斥锁契约（失败降级语义由调用方承担）。

    与 agent 域的同名端口同形：``run:{conversation_id}`` 与
    ``consolidation:{agent_id}`` 共用这一原语。
    """

    def acquire(self, name: str, timeout: int) -> bool:
        """尝试获取命名锁（0 = 立即返回）。"""
        ...

    def release(self, name: str) -> None:
        """释放命名锁（连接断开时由 MySQL 自愈）。"""
        ...
