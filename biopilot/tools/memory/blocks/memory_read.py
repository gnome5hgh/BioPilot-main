"""MemoryReadTool：按 label 读记忆块当前值（只读）。"""
from biopilot.core.tool import Tool, ToolResult
from biopilot.tools.memory.runtime_context import get_memory_context

__all__ = ["MemoryReadTool"]


class MemoryReadTool(Tool):
    """按 label 读单个记忆块的当前值（只读）。

    定向增改（memory_replace 要给 old_string、memory_apply_patch 要对着当前
    内容写 diff）都以「已经看到当前内容」为前提，本工具是它们的预读通道；
    也是核对块现状的通用读入口。

    Attributes:
        name: str，工具名 "memory_read"
        description: str，工具描述
        parameters: dict，JSON Schema（label）
        risk_level: str，"low"（纯只读）
    """

    name = "memory_read"
    description = "按 label 读记忆块的当前值（只读）；memory_replace/memory_apply_patch 前先读"
    parameters = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
    }
    risk_level = "low"    # 纯只读

    def execute(self, label: str) -> ToolResult:
        """按 label 读块；错误一律降级为文本返回。

        Args:
            label: str，目标块标签

        Returns:
            ToolResult，文本为块内容（带版本号与描述头）；块不存在时如实说明。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            block = ctx.block_manager.get_block_by_label(label)
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
        if block is None:
            return ToolResult(text=f"block {label} not found")
        head = f"description: {block.description}\n" if block.description else ""
        return ToolResult(text=f"[{label}] v{block.version}\n{head}{block.value}")
