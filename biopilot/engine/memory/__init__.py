"""biopilot 核心记忆子系统。

对外统一导出记忆栈组件：领域模型（entity 压缩产物 / dto 整合指令契约）、schema
数据模型、MySQL 存储层、服务层（块/消息/agent 管理器）、压缩配置、
MemoryConsolidator 后台整合与常量。分层依赖单向：constants/domain（schemas/entity/dto/errors/ports）→ application（编排）→
adapters（MySQL 持久化与命名锁）；对外工具面经 biopilot.engine.tools 的只读召回消费。
"""
from biopilot.engine.memory.domain.schemas.block import BaseBlock, Block
from biopilot.engine.memory.domain.schemas.memory import Memory
from biopilot.engine.memory.domain.schemas.stored_message import StoredMessage
from biopilot.engine.memory.domain.schemas.agent import AgentState
from biopilot.engine.memory.domain.dto.memory_edit import MemoryEdit
from biopilot.engine.memory.domain.dto.memory_edit_batch import MemoryEditBatch
from biopilot.engine.memory.domain.entity.summary import Summary
from biopilot.engine.memory.adapters.database import MemoryDB
from biopilot.engine.memory.application.block_manager import BlockManager
from biopilot.engine.memory.application.message_manager import MessageManager
from biopilot.engine.memory.application.agent_manager import AgentManager
from biopilot.engine.memory.application.compaction import (
    CompactionSettings, ContextSize)
from biopilot.engine.memory.application.consolidation import MemoryConsolidator
from biopilot.engine.memory import constants

__all__ = [
    "BaseBlock", "Block", "Memory", "StoredMessage",
    "AgentState", "MemoryDB",
    "MemoryEdit", "MemoryEditBatch",
    "Summary",
    "BlockManager", "MessageManager",
    "AgentManager",
    "CompactionSettings", "ContextSize", "MemoryConsolidator", "constants",
]
