"""MemoryTool：统一记忆块管理（create / replace / delete / rename）。"""
from biopilot.core.memory.services.block_management import manage_block
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context


class MemoryTool(Tool):
    """统一记忆块管理工具（create/replace/delete/rename 四动作分发）。

    Attributes:
        name: str，工具名 "memory"
        description: str，工具描述（告诉模型何时用）
        parameters: dict，JSON Schema（action/label/value）
        risk_level: str，"medium"（写入类）
    """
    name = "memory"
    description = "统一记忆块管理（create/replace/delete/rename）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "replace", "delete", "rename"]},
            "label": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["action", "label"],
    }
    risk_level = "medium"

    def execute(self, action: str, label: str, value: str | None = None,
                **kwargs) -> ToolResult:
        """按 action 分发到块的增改删查；错误一律降级为文本返回。

        Args:
            action: create | replace | delete | rename。
            label: 目标块标签。
            value: 块内容（create/replace 用）；rename 时可作 new_label 兜底。
            kwargs: rename 时的新标签 new_label。

        Returns:
            ToolResult；未装配记忆服务/标签冲突/只读/未知动作都降级为文本。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            return ToolResult(text=manage_block(ctx.block_manager, action, label,
                                                value, **kwargs))
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
