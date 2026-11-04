# biopilot/tools/file/read_reference.py
"""ReadReferenceTool：读取本角色参考资料目录中的文件（模板等）。

内置流程的模板（笔记模板、选题四份模板）不再随 skill 分发，而是作为 agent 插件
自己的 `references/` 资源。每个角色在 `tools.py` 里用本文件所在目录构造工具：
基目录在构造期固定，运行期只接受目录内相对路径——与 `load_skill` 的资源围栏同一思路，
但作用域是「本角色的参考资料」，不依赖部署路径，也不扩大通用 `read_file` 的暴露面。
"""

from pathlib import Path

from biopilot.engine.tool import Tool, ToolResult


class ReadReferenceTool(Tool):
    """读取本角色 `references/` 下的文本资料（只读）。

    Attributes:
        name: str，工具名 "read_reference"
        description: str，工具描述（相对路径 + 只读）
        parameters: dict，JSON Schema（name）
        risk_level: str，"low"（只读）
        side_effects: list[str]，["read_file"]
        provenance: str，"local_file"（外部内容打来源标记）
        _base: Path，本角色参考资料目录（构造期 resolve）
    """

    name = "read_reference"
    description = (
        "读取本角色参考资料（references/）中的文本文件。name 用相对路径，"
        "例如 paper_note.md 或 references/paper_note.md。只读、不写。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "相对本角色 references 目录的路径，如 paper_note.md",
            },
        },
        "required": ["name"],
    }
    risk_level = "low"
    side_effects = ["read_file"]
    provenance = "local_file"

    def __init__(self, base_dir: str | Path):
        """绑定参考资料目录。

        Args:
            base_dir: 本角色的 references 目录（构造期 resolve 成绝对路径）。
        """
        super().__init__()
        self._base = Path(base_dir).resolve()

    def execute(self, name: str) -> ToolResult:
        """读取参考资料文件。

        Args:
            name: 相对参考资料目录的路径（如 paper_note.md）。

        Returns:
            ToolResult，文本为文件内容；越界、缺失或非文本时返回错误文本。
        """
        target = (self._base / str(name or "")).resolve()
        if not target.is_relative_to(self._base):
            return ToolResult(text=f"读取被拒绝：{name} 越出本角色参考资料目录", is_error=True)
        if target.is_dir():
            return ToolResult(text=f"{name} 是目录，不是文件", is_error=True)
        try:
            return ToolResult(text=target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ToolResult(text=f"参考资料不存在：{name}", is_error=True)
        except UnicodeDecodeError:
            return ToolResult(text=f"{name} 不是 UTF-8 文本", is_error=True)
        except OSError as e:
            return ToolResult(text=f"读取失败：{type(e).__name__}: {e}", is_error=True)
