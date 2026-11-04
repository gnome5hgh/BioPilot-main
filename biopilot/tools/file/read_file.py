"""ReadFileTool：读取平台文件/文档的文本内容。

模型只接触 ``file_id`` / ``doc_id`` / 文档名，不接触本地路径；字节由 Java 内部端点
按 ``X-User-Id`` 取回。读取失败降级为可行动文本，不抛进 ReAct 循环。
"""
from biopilot.common.platform import PlatformError
from biopilot.core.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class ReadFileTool(Tool):
    """读取平台文本文件或文档的只读工具。

    Attributes:
        name: str，工具名 "read_file"
        description: str，工具描述
        parameters: dict，JSON Schema（id/name/kind）
        risk_level: str，"low"（只读）
        side_effects: list[str]，["read_file"]
    """
    name = "read_file"
    description = ("读取平台文件/文档的文本内容（UTF-8）。文档用 id 或 name 定位；"
                   "数据文件/分析产物用 id 定位。论文 PDF 用 read_pdf。")
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "file_id",
                   "description": "文档/文件 id（与 name 二选一）"},
            "name": {"type": "string", "format": "file_name",
                     "description": "文档名（仅 document；与 id 二选一）"},
            "kind": {"type": "string", "enum": ["document", "data", "artifact"],
                     "description": "文件类型；默认 document"},
        },
    }
    risk_level = "low"
    provenance = "local_file"
    side_effects = ["read_file"]

    def execute(self, id: str | None = None, name: str | None = None,
                kind: str = "document") -> ToolResult:
        """读取文档正文或数据文件字节并解码为 UTF-8。

        Args:
            id: 文档/文件 id。
            name: 文档名（仅 document）。
            kind: document/data/artifact。

        Returns:
            ToolResult，文本为内容；参数缺失/不存在/非 UTF-8 时返回错误文本。
        """
        user = current_user_id()
        platform = platform_for(self)
        try:
            if kind == "document":
                if id:
                    doc = platform.get_document(user, id)
                elif name:
                    doc = platform.get_document_by_name(user, name)
                else:
                    return ToolResult(text="read_file 需要 id 或 name（document）", is_error=True)
                return ToolResult(text=str(doc.get("content") or ""))
            if not id:
                return ToolResult(text=f"read_file 读取 {kind} 需要 id", is_error=True)
            data, meta = platform.attachment(user, "file", id)
            if (meta.get("content_type") or "").lower() == "application/pdf":
                return ToolResult(text="这是 PDF，请用 read_pdf 读取", is_error=True)
            try:
                return ToolResult(text=data.decode("utf-8"))
            except UnicodeDecodeError:
                return ToolResult(
                    text=f"{meta.get('name') or id} 不是 UTF-8 文本，read_file 读不了",
                    is_error=True)
        except PlatformError as e:
            return ToolResult(text=f"读取失败：{e}", is_error=True)
        finally:
            platform.close()
