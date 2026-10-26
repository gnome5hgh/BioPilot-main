"""记忆领域模型：跨包共享的数据契约——entity/ 放持久领域对象，dto/ 放层间搬运的瞬态载体。"""
from paperflow.core.memory.domain.dto.memory_edit import MemoryEdit
from paperflow.core.memory.domain.dto.memory_edit_batch import MemoryEditBatch
from paperflow.core.memory.domain.entity.compaction_result import CompactionResult
from paperflow.core.memory.domain.entity.summary import Summary
from paperflow.core.memory.domain.entity.task_snapshot import TaskSnapshot

__all__ = ["CompactionResult", "Summary", "TaskSnapshot", "MemoryEdit",
           "MemoryEditBatch"]
