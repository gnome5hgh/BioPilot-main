"""MemoryRethinkTool：整块重写记忆。"""
from biopilot.core.memory.services.block_edit import rewrite_block
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context


class MemoryRethinkTool(Tool):
    """整块重写记忆的工具。

    Attributes:
        name: str，工具名 "memory_rethink"
        description: str，工具描述
        parameters: dict，JSON Schema（label/new_memory）
        risk_level: str，"medium"
    """
    name = "memory_rethink"
    description = "整块重写记忆"
    parameters = {
        "type": "object",
        "properties": {"label": {"type": "string"}, "new_memory": {"type": "string"}},
        "required": ["label", "new_memory"],
    }
    risk_level = "medium"

    def execute(self, label: str, new_memory: str) -> ToolResult:
        """整块重写：read_only 报错由 rewrite_block 吞掉；缺失块落到外层降级。

        Args:
            label: 目标块标签。
            new_memory: 新的整块内容。

        Returns:
            ToolResult；read_only/超限由 rewrite_block 吞为错误文本，块缺失落到外层降级。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            return ToolResult(text=rewrite_block(ctx.block_manager, label, new_memory))
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
