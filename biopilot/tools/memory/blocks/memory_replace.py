"""MemoryReplaceTool：替换记忆块中的精确子串（old_string 必须唯一）。"""
from biopilot.core.memory.services.block_edit import replace_unique
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context


class MemoryReplaceTool(Tool):
    """替换记忆块中精确子串的工具（old_string 必须唯一）。

    Attributes:
        name: str，工具名 "memory_replace"
        description: str，工具描述
        parameters: dict，JSON Schema（label/old_string/new_string）
        risk_level: str，"medium"
    """
    name = "memory_replace"
    description = "替换记忆块中的精确子串（old_string 必须唯一）"
    parameters = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "记忆块标签"},
            "old_string": {"type": "string", "description": "要替换的旧子串（必须唯一）"},
            "new_string": {"type": "string", "description": "新子串"},
        },
        "required": ["label", "old_string", "new_string"],
    }
    risk_level = "medium"

    def execute(self, label: str, old_string: str, new_string: str) -> ToolResult:
        """替换记忆块中的精确子串（old_string 必须唯一）。

        Args:
            label: 目标块标签。
            old_string: 待替换的旧子串（须唯一）。
            new_string: 新子串。

        Returns:
            ToolResult；未装配记忆服务时返回不可用提示，其余异常降级为错误文本。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            return ToolResult(text=replace_unique(ctx.block_manager, label,
                                                  old_string, new_string))
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
