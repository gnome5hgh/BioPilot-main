"""MemoryInsertTool：在记忆块指定行号后插入内容（-1=末尾，0=开头）。"""
from biopilot.core.memory.services.block_edit import insert_line as insert_block_line
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context


class MemoryInsertTool(Tool):
    """在记忆块指定行号后插入内容的工具。

    Attributes:
        name: str，工具名 "memory_insert"
        description: str，工具描述
        parameters: dict，JSON Schema（label/new_string/insert_line）
        risk_level: str，"medium"
    """
    name = "memory_insert"
    description = "在记忆块指定行插入内容"
    parameters = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "new_string": {"type": "string"},
            "insert_line": {"type": "integer", "description": "插入行号；-1=末尾，0=开头"},
        },
        "required": ["label", "new_string"],
    }
    risk_level = "medium"

    def execute(self, label: str, new_string: str, insert_line: int = -1) -> ToolResult:
        """在记忆块指定行号后插入内容（-1=末尾）。

        Args:
            label: 目标块标签。
            new_string: 待插入内容。
            insert_line: 插入行号（-1=末尾，0=开头）。

        Returns:
            ToolResult；未装配记忆服务时返回不可用提示，其余异常降级为错误文本。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            return ToolResult(text=insert_block_line(ctx.block_manager, label,
                                                     new_string, insert_line))
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
