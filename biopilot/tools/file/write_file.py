"""WriteFileTool：把文本写入平台文档或分析产物。

不再接受本地路径：文档走 ``/internal/documents/save``（同名覆盖、OSS 落盘），
分析产物走 ``/internal/files/artifacts``（不占用户可见名字）。
"""
from biopilot.common.platform import PlatformError
from biopilot.engine.tool import Tool, ToolResult
from biopilot.tools.file._support import (
    content_type_for, current_run_id, current_user_id, normalize_name, platform_for,
)


class WriteFileTool(Tool):
    """写入平台文档或分析产物的工具。

    Attributes:
        name: str，工具名 "write_file"
        description: str，工具描述
        parameters: dict，JSON Schema（name/content/kind）
        risk_level: str，"high"（覆盖型写）
        side_effects: list[str]，["write_file"]
    """
    name = "write_file"
    description = ("把文本保存到平台：kind=document（默认）按名字写入文档编辑器，"
                   "同名覆盖；kind=artifact 作为分析产物入库（返回 file_id）。"
                   "不再接受本地路径。")
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "format": "file_name",
                     "description": "文件名/文档名（如 笔记.md）"},
            "content": {"type": "string", "format": "content",
                        "description": "完整文本内容"},
            "kind": {"type": "string", "enum": ["document", "artifact"],
                     "description": "document=文档编辑器；artifact=分析产物；默认 document"},
        },
        "required": ["name", "content"],
    }
    risk_level = "high"
    side_effects = ["write_file"]

    def execute(self, name: str, content: str, kind: str = "document") -> ToolResult:
        """写入平台文档或分析产物。

        Args:
            name: 文件名/文档名。
            content: 完整文本。
            kind: document 或 data。

        Returns:
            ToolResult，文本含 id/版本；平台失败时为错误文本。
        """
        user = current_user_id()
        platform = platform_for(self)
        try:
            if kind == "artifact":
                created = platform.upload_artifact(
                    user, current_run_id(), name, (content or "").encode("utf-8"),
                    content_type_for(name))
                return ToolResult(
                    text=(f"已保存分析产物 {created.get('name') or name}"
                          f"（file_id={created.get('file_id')}）"))
            saved = platform.save_document(user, name, content or "")
            return ToolResult(
                text=(f"已保存文档《{saved.get('name') or name}》"
                      f"（id={saved.get('id')}，version={saved.get('version')}）"))
        except PlatformError as e:
            return ToolResult(text=f"保存失败：{e}", is_error=True)
        finally:
            platform.close()

    def effective_target_key(self, args: dict) -> str | None:
        """确认键作用域：文档按归一化名，产物按名字。"""
        name = args.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        kind = args.get("kind") or "document"
        user = current_user_id()
        if kind == "artifact":
            return f"file:{user}:{name.strip()}"
        return f"name:{user}:{normalize_name(name)}"
