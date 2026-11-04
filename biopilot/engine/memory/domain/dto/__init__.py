"""记忆领域 dto：层间搬运的契约载体（LLM 结构化输出，产出即消费、不落库）。

与 `../entity/` 的分工：entity 放压缩产物等持久领域对象，dto 放瞬态指令契约。
消费方从本包门面取，勿深入子模块。
"""
from biopilot.engine.memory.domain.dto.memory_edit import MemoryEdit
from biopilot.engine.memory.domain.dto.memory_edit_batch import MemoryEditBatch

__all__ = ["MemoryEdit", "MemoryEditBatch"]
