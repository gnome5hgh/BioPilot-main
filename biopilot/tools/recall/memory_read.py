"""MemoryReadTool：读长期记忆块（只读，装配给所有 agent）。"""
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context

__all__ = ["MemoryReadTool"]


class MemoryReadTool(Tool):
    """读长期记忆块（只读）。

    长期记忆的写入统一由后台整合完成，任何 agent 都不持有写工具；本工具只提供
    读取通道：不传 label 时列出块清单，传 label 时返回该块当前内容。块清单是
    必要的——分册 label 由日期拼装，调用方不可能预先知道。

    Attributes:
        name: str，工具名 "memory_read"
        description: str，工具描述
        parameters: dict，JSON Schema（label 可选）
        risk_level: str，"low"（纯只读）
    """

    name = "memory_read"
    description = (
        "读长期记忆块（只读）。不传 label 时列出所有块的 label/描述/字数；"
        "传 label 时返回该块当前内容。")
    parameters = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
    }
    risk_level = "low"    # 纯只读

    def execute(self, label: str | None = None) -> ToolResult:
        """读一个块或列出全部块；错误一律降级为文本返回。

        Args:
            label: str | None，目标块标签；None 表示列出全部块。

        Returns:
            ToolResult，文本为块内容或块清单；块不存在/未装配时如实说明。
        """
        ctx = get_memory_context()
        if ctx is None:
            return ToolResult(text="记忆服务未装配，记忆工具不可用")
        try:
            blocks = ctx.block_manager.list_blocks()
        except Exception as e:
            return ToolResult(text=f"Error: {e}")
        if label is None:
            if not blocks:
                return ToolResult(text="（没有记忆块）")
            lines = ["可读的长期记忆块（传 label 读取内容）："]
            for b in blocks:
                desc = f" — {b.description}" if b.description else ""
                lines.append(f"- {b.label}{desc}（{len(b.value)} 字）")
            return ToolResult(text="\n".join(lines))
        block = next((b for b in blocks if b.label == label), None)
        if block is None:
            return ToolResult(text=f"block {label} not found")
        head = f"description: {block.description}\n" if block.description else ""
        return ToolResult(text=f"[{label}] v{block.version}\n{head}{block.value}")
