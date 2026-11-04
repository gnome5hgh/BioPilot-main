"""GrepTool：在平台文档内按正则搜文本（只读）。

不再递归本地目录：按 id/name 搜单篇，或列最近文档后逐篇取正文搜索。返回
``document id name line:text``，命中行原样返回，便于作为 edit_file 的锚点。
"""
import re

from biopilot.common.platform import PlatformError
from biopilot.engine.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class GrepTool(Tool):
    """在平台文档内按正则搜文本的只读工具。

    Attributes:
        name: str，工具名 "grep"
        description: str，工具描述
        parameters: dict，JSON Schema（pattern/id/name/limit）
        risk_level: str，"low"（只读）
    """
    name = "grep"
    description = ("在平台文档内搜索文本（正则），返回 document id name line:text。"
                   "给 id/name 搜单篇；都不给时搜索最近文档（最多 20 篇）。")
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "正则表达式"},
            "id": {"type": "string", "format": "file_id",
                   "description": "只搜这一篇文档 id"},
            "name": {"type": "string", "format": "file_name",
                     "description": "只搜这一篇文档名"},
            "limit": {"type": "integer", "description": "最多返回条数；默认 30"},
        },
        "required": ["pattern"],
    }
    risk_level = "low"
    provenance = "local_file"

    def execute(self, pattern: str, id: str | None = None,
                name: str | None = None, limit: int = 30) -> ToolResult:
        """在平台文档内按正则搜索文本。

        Args:
            pattern: 正则表达式。
            id: 只搜该文档 id。
            name: 只搜该文档名。
            limit: 最多返回条数。

        Returns:
            ToolResult，每行 ``document id name line:text``；无匹配返回“无匹配”。
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(text=f"正则无效: {e}", is_error=True)
        user = current_user_id()
        platform = platform_for(self)
        cap = max(1, min(int(limit or 30), 100))
        hits: list[str] = []
        try:
            docs: list[dict] = []
            if id:
                docs = [platform.get_document(user, id)]
            elif name:
                docs = [platform.get_document_by_name(user, name)]
            else:
                docs = platform.list_documents(user)[:20]
            for meta in docs:
                doc_id = str(meta.get("id") or "")
                doc_name = str(meta.get("name") or "")
                content = meta.get("content")
                if content is None:
                    content = platform.get_document(user, doc_id).get("content")
                for line_no, line in enumerate(str(content or "").splitlines(), 1):
                    if regex.search(line):
                        hits.append(f"{doc_id}\t{doc_name}\t{line_no}:{line}")
                        if len(hits) >= cap:
                            return ToolResult(text="\n".join(hits))
            return ToolResult(text="\n".join(hits) if hits else "无匹配")
        except PlatformError as e:
            return ToolResult(text=f"搜索失败：{e}", is_error=True)
        finally:
            platform.close()
