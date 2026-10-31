"""biopilot 核心记忆子系统。

对外统一导出记忆栈组件：领域模型（entity 压缩产物 / dto 整合指令契约）、schema
数据模型、SQLite 存储层、服务层（块/消息/agent 管理器 + MemFS）、压缩配置、
MemoryConsolidator 后台整合与常量。分层依赖单向：constants/schemas/domain/common → storage → services → tools。
"""
from biopilot.core.memory.schemas.block import BaseBlock, Block
from biopilot.core.memory.schemas.memory import Memory
from biopilot.core.memory.schemas.stored_message import StoredMessage
from biopilot.core.memory.schemas.agent import AgentState
from biopilot.core.memory.domain.dto.memory_edit import MemoryEdit
from biopilot.core.memory.domain.dto.memory_edit_batch import MemoryEditBatch
from biopilot.core.memory.domain.entity.compaction_result import CompactionResult
from biopilot.core.memory.domain.entity.summary import Summary
from biopilot.core.memory.domain.entity.task_snapshot import TaskSnapshot
from biopilot.core.memory.storage.database import MemoryDB
from biopilot.core.memory.services.block_manager import BlockManager, GitEnabledBlockManager
from biopilot.core.memory.services.memfs import MemFS
from biopilot.core.memory.services.message_manager import MessageManager
from biopilot.core.memory.services.agent_manager import AgentManager
from biopilot.core.memory.services.compaction import (
    CompactionSettings, ContextSize)
from biopilot.core.memory.services.consolidation import MemoryConsolidator
from biopilot.core.memory import constants

__all__ = [
    "BaseBlock", "Block", "Memory", "StoredMessage",
    "AgentState", "MemoryDB",
    "MemoryEdit", "MemoryEditBatch",
    "CompactionResult", "Summary", "TaskSnapshot",
    "BlockManager", "GitEnabledBlockManager", "MemFS", "MessageManager",
    "AgentManager",
    "CompactionSettings", "ContextSize", "MemoryConsolidator", "constants",
]
