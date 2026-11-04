"""DeleteFileTool：删除平台文档或数据文件/分析产物。

删除不可逆：文档按 id/名字删，数据文件与产物按 id 删。对象由 Java 在行删除后
交给 GC，失败只留孤儿，不会留下指向不存在对象的行。
"""
from biopilot.common.platform import PlatformError
from biopilot.core.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class DeleteFileTool(Tool):
    """删除平台文件的写入类工具（需用户确认）。

    Attributes:
        name: str，工具名 "delete_file"
        description: str，工具描述
        parameters: dict，JSON Schema（kind/id/name）
        risk_level: str，"critical"
        side_effects: list[str]，["delete_file"]
    """
    name = "delete_file"
    description = ("删除一个平台文件（不可逆）。kind=document 时用 id 或 name；"
                   "kind=data/artifact 时必须用 id。不支持通配符、不支持批量。")
    parameters = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["document", "data", "artifact"],
                     "description": "文件类型"},
            "id": {"type": "string", "format": "file_id",
                   "description": "文件/文档 id"},
            "name": {"type": "string", "format": "file_name",
                     "description": "文档名（仅 document）"},
        },
        "required": ["kind"],
    }
    risk_level = "critical"
    side_effects = ["delete_file"]

    def execute(self, kind: str, id: str | None = None,
                name: str | None = None) -> ToolResult:
        """删除平台文档/数据文件/产物。

        Args:
            kind: document/data/artifact。
            id: 文件或文档 id。
            name: 文档名（document 且没有 id 时使用）。

        Returns:
            ToolResult；参数缺失/不存在/平台失败时返回错误文本。
        """
        user = current_user_id()
        platform = platform_for(self)
        try:
            if kind == "document":
                doc_id = id
                if not doc_id and name:
                    doc_id = str(platform.get_document_by_name(user, name).get("id") or "")
                if not doc_id:
                    return ToolResult(text="删除文档需要 id 或 name", is_error=True)
                platform.delete_document(user, doc_id)
                return ToolResult(text=f"已删除文档 {doc_id}")
            if not id:
                return ToolResult(text=f"删除 {kind} 需要 id", is_error=True)
            platform.delete_file(user, id)
            return ToolResult(text=f"已删除 {kind} {id}")
        except PlatformError as e:
            return ToolResult(text=f"删除失败：{e}", is_error=True)
        finally:
            platform.close()

    def effective_target_key(self, args: dict) -> str | None:
        """确认键作用域：文档 id/名字，或文件 id。"""
        user = current_user_id()
        kind = args.get("kind") or "document"
        if args.get("id"):
            return f"{kind}:{user}:{args['id']}"
        name = args.get("name")
        if isinstance(name, str) and name.strip():
            return f"name:{user}:{name.strip().lower()}"
        return None
