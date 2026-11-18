"""memory 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

本模块是 ``biopilot.engine.memory`` 对外的唯一声明处：模块外的调用方（FastAPI
侧、其它 engine 模块）一律 ``from biopilot.engine.memory.adapters.api import ...``
或经包根别名（根只做本文件的再导出）。出向实现（MySQL 池与 SQL、命名锁）同住
``adapters/``，同属公开面。

``build_memory`` 是本模块唯一的组装入口：把共享连接池、四个仓储与三个 manager
接成一个用户域的记忆栈；整合器的锁工厂也在这里给出（每次整合现取一把命名锁）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from biopilot.engine.memory.adapters.agent_state import MySqlAgentStateRepository
from biopilot.engine.memory.adapters.block import MySqlBlockRepository
from biopilot.engine.memory.adapters.conversation import (
    delete_consolidation_cursor, delete_conversation, get_title, list_context_rows,
    list_history, list_sessions, mark_user_deleting, purge_user, set_title,
    update_message_meta,
)
from biopilot.engine.memory.adapters.cursor import MySqlConsolidationCursorStore
from biopilot.engine.memory.adapters.database import MemoryDB
from biopilot.engine.memory.adapters.message import MySqlMessageRepository
from biopilot.engine.memory.adapters.named_lock import NamedLock
from biopilot.engine.memory.application.agent_manager import AgentManager
from biopilot.engine.memory.application.block_manager import BlockManager
from biopilot.engine.memory.application.compaction import (
    CompactionSettings, blend_token_ratio, estimate_tokens, run_compaction,
    should_compress,
)
from biopilot.engine.memory.application.consolidation import (
    ConsolidationQueue, MemoryConsolidator,
)
from biopilot.engine.memory.application.message_manager import MessageManager
from biopilot.engine.memory.domain.dto.memory_edit import MemoryEdit
from biopilot.engine.memory.domain.dto.memory_edit_batch import MemoryEditBatch
from biopilot.engine.memory.domain.entity.summary import Summary
from biopilot.engine.memory.domain.ports import (
    AgentStateRepository, AgentStateStore, BlockRepository,
    ConsolidationCursorStore, MemoryBlockReader, MessageRepository,
    MessageStore, RunMutex,
)
from biopilot.engine.memory.domain.schemas.agent import AgentState
from biopilot.engine.memory.domain.schemas.block import BaseBlock, Block
from biopilot.engine.memory.domain.schemas.memory import Memory
from biopilot.engine.memory.domain.schemas.stored_message import StoredMessage

__all__ = [
    # 公开类型（领域词汇）
    "BaseBlock", "Block", "Memory", "StoredMessage", "AgentState",
    "MemoryEdit", "MemoryEditBatch", "Summary", "CompactionSettings",
    # 端口（其它模块 / 测试的类型面）
    "MessageStore", "AgentStateStore", "MemoryBlockReader",
    "BlockRepository", "MessageRepository", "AgentStateRepository",
    "ConsolidationCursorStore", "RunMutex",
    # 应用服务（编排面）
    "BlockManager", "MessageManager", "AgentManager",
    "MemoryConsolidator", "ConsolidationQueue",
    # 压缩助手
    "estimate_tokens", "should_compress", "run_compaction", "blend_token_ratio",
    # 出向实现（同属公开面：MySQL 池与命名锁）
    "MemoryDB", "NamedLock",
    # 会话级轻量查询与清理
    "get_title", "set_title", "list_history", "list_context_rows",
    "update_message_meta", "delete_conversation", "list_sessions",
    "mark_user_deleting", "delete_consolidation_cursor", "purge_user",
    # 组装
    "build_memory", "MemoryHandle", "shared_db",
]


@dataclass
class MemoryHandle:
    """一个用户域的记忆栈：manager 与端口实例的集合。

    Attributes:
        db: MemoryDB，共享连接池（组装根复用同一口池）。
        block_manager: BlockManager，块 CRUD 服务。
        message_manager: MessageManager，消息落盘与窗口回放。
        agent_manager: AgentManager，会话状态服务。
        cursor_store: ConsolidationCursorStore，整合游标端口。
        lock_factory: Callable[[], RunMutex]，跨进程锁工厂（整合消费权用）。
    """

    db: MemoryDB
    block_manager: BlockManager
    message_manager: MessageManager
    agent_manager: AgentManager
    cursor_store: ConsolidationCursorStore
    lock_factory: Callable[[], RunMutex]


def shared_db(dsn: str | None = None) -> MemoryDB:
    """取进程级共享连接池（按 DSN 单例；轻量 SQL 与会话装配同一口池）。

    Args:
        dsn: 连接串；None 时按环境变量取。

    Returns:
        MemoryDB：共享池。
    """
    return MemoryDB.shared(dsn)


def build_memory(db: MemoryDB | None = None, *,
                 user_id: str) -> MemoryHandle:
    """装配一个用户域的记忆栈（模块对外唯一的组装入口）。

    Args:
        db: 可选连接；None 时取进程级共享池。
        user_id: 归属用户（行级隔离键，必填）。

    Returns:
        MemoryHandle：manager 与端口实例的集合。

    Raises:
        ValueError: user_id 为空。
    """
    db = db or MemoryDB.shared()
    blocks_repo = MySqlBlockRepository(db, user_id=user_id)
    messages_repo = MySqlMessageRepository(db)
    state_repo = MySqlAgentStateRepository(db)
    cursor_repo = MySqlConsolidationCursorStore(db)

    block_manager = BlockManager(blocks_repo, user_id=user_id)
    agent_manager = AgentManager(state_repo, messages_repo, block_manager,
                                 cursor_repo)
    message_manager = MessageManager(messages_repo, agent_state=agent_manager)
    lock_factory = (lambda: NamedLock(db.dsn)) if db.dsn else None
    return MemoryHandle(
        db=db, block_manager=block_manager, message_manager=message_manager,
        agent_manager=agent_manager, cursor_store=cursor_repo,
        lock_factory=lock_factory,
    )
