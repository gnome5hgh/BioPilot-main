"""MemoryApplyPatchTool：就地应用简化 unified diff（仅单块模式）。"""
from biopilot.core.memory.services.block_patch import apply_patch
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context


class MemoryApplyPatchTool(Tool):
    """用简化 unified diff 更新记忆块的工具（仅单块模式）。

    Attributes:
        name: str，工具名 "memory_apply_patch"
        description: str，工具描述
        parameters: dict，JSON Schema（label/patch）
        risk_level: str，"medium"
    """
    name = "memory_apply_patch"
    description = "用简化 unified diff 更新记忆块"
    parameters = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "patch": {"type": "string", "description": "简化 unified diff"},
        },
        "required": ["label", "patch"],
    }
    risk_level = "medium"

    def execute(self, label: str, patch: str) -> ToolResult:
        """对指定记忆块应用简化 unified diff。

        Args:
            label: 目标块标签。
            patch: 简化 unified diff。

        Returns:
            ToolResult；未装配记忆服务时返回不可用提示，其余异常降级为错误文本。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            return ToolResult(text=apply_patch(ctx.block_manager, label, patch))
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
