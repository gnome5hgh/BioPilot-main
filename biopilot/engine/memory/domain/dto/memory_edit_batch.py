"""记忆整合的编辑指令批次契约：一次整合 LLM 调用的输出，整批预验证、逐条应用。"""
from pydantic import BaseModel, Field

from biopilot.engine.memory.domain.dto.memory_edit import MemoryEdit

__all__ = ["MemoryEditBatch"]


class MemoryEditBatch(BaseModel):
    """一次整合会话的编辑指令集合（上限 20 条，防单轮过量写入）。

    Attributes:
        edits: list[MemoryEdit]，本轮整合的编辑指令（上限 20 条）
    """

    edits: list[MemoryEdit] = Field(default_factory=list, max_length=20)
