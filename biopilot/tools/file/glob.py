"""GlobTool：按名字模式列出平台文档/文件。

不再扫描本地目录；模型用文件名模式在平台清单里定位资源，返回 ``kind id name``。
只读 → low 风险、无需确认。
"""
import fnmatch

from biopilot.common.platform import PlatformError
from biopilot.engine.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class GlobTool(Tool):
    """按名字模式列出平台文件的只读工具。

    Attributes:
        name: str，工具名 "glob"
        description: str，工具描述
        parameters: dict，JSON Schema（pattern/kind/limit）
        risk_level: str，"low"（只读）
    """
    name = "glob"
    description = ("按名字模式列出平台文档/数据文件（如 *.md、*qc*）。"
                   "返回 kind id name；用 read_file 读取内容。")
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "文件名模式（支持 * ?）"},
            "kind": {"type": "string",
                     "enum": ["all", "document", "data", "artifact"],
                     "description": "类型过滤；默认 all"},
            "limit": {"type": "integer", "description": "最多返回条数；默认 50"},
        },
        "required": ["pattern"],
    }
    risk_level = "low"

    def execute(self, pattern: str = "*", kind: str = "all",
                limit: int = 50) -> ToolResult:
        """按名字模式列出平台文件。

        Args:
            pattern: 文件名模式（大小写不敏感）。
            kind: all/document/data/artifact。
            limit: 最多返回条数。

        Returns:
            ToolResult，每行 ``kind id name``；无匹配返回“无匹配”。
        """
        user = current_user_id()
        platform = platform_for(self)
        cap = max(1, min(int(limit or 50), 200))
        rows: list[tuple[str, str, str]] = []
        try:
            if kind in ("all", "document"):
                for doc in platform.list_documents(user):
                    name = str(doc.get("name") or "")
                    if fnmatch.fnmatch(name.lower(), pattern.lower()):
                        rows.append(("document", str(doc.get("id") or ""), name))
            if kind in ("all", "data", "artifact"):
                for item in platform.list_files(user, limit=200):
                    item_kind = str(item.get("kind") or "data")
                    if kind != "all" and item_kind != kind:
                        continue
                    name = str(item.get("name") or "")
                    if fnmatch.fnmatch(name.lower(), pattern.lower()):
                        rows.append((item_kind, str(item.get("id") or ""), name))
            if not rows:
                return ToolResult(text="无匹配")
            return ToolResult(text="\n".join(
                f"{k}\t{i}\t{n}" for k, i, n in rows[:cap]))
        except PlatformError as e:
            return ToolResult(text=f"列出文件失败：{e}", is_error=True)
        finally:
            platform.close()
