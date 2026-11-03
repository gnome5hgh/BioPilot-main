"""EditFileTool：对平台文档做定向 search-replace。

读取文档正文 → 内存替换 → 带版本号写回。版本冲突返回 409 文本，由模型重新读取后
重试；不再读写本地文件。
"""
from biopilot.common.platform import PlatformError
from biopilot.core.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class EditFileTool(Tool):
    """定向修改平台文档的工具（search-replace）。

    Attributes:
        name: str，工具名 "edit_file"
        description: str，工具描述
        parameters: dict，JSON Schema（id/name/old_text/new_text）
        risk_level: str，"high"
        side_effects: list[str]，["write_file"]
    """
    name = "edit_file"
    description = ("定向修改平台文档（search-replace，须精确匹配 old_text）。"
                   "用 id 或 name 定位文档；版本冲突时先 read_file 读取最新内容再重试。")
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "file_id",
                   "description": "文档 id（与 name 二选一）"},
            "name": {"type": "string", "format": "file_name",
                     "description": "文档名（与 id 二选一）"},
            "old_text": {"type": "string", "format": "content",
                         "description": "要替换的原文（须精确且唯一）"},
            "new_text": {"type": "string", "format": "content",
                         "description": "替换后的文本"},
        },
        "required": ["old_text", "new_text"],
    }
    risk_level = "high"
    root_hints = []
    side_effects = ["write_file"]

    def execute(self, old_text: str, new_text: str, id: str | None = None,
                name: str | None = None) -> ToolResult:
        """在平台文档里精确替换一处 old_text。

        Args:
            old_text: 待替换原文（须唯一命中）。
            new_text: 替换后的文本。
            id: 文档 id。
            name: 文档名。

        Returns:
            ToolResult；未命中/多次命中/版本冲突都返回可行动文本。
        """
        if not old_text:
            return ToolResult(text="old_text 不能为空，请提供要替换的原文")
        user = current_user_id()
        platform = platform_for(self)
        try:
            if id:
                doc = platform.get_document(user, id)
            elif name:
                doc = platform.get_document_by_name(user, name)
            else:
                return ToolResult(text="edit_file 需要 id 或 name", is_error=True)
            content = str(doc.get("content") or "")
            count = content.count(old_text)
            if count == 0:
                return ToolResult(text="未找到要替换的文本，请先用 read_file 确认当前内容")
            if count > 1:
                return ToolResult(text=f"待替换文本出现 {count} 次，请提供更长的唯一锚点")
            saved = platform.save_document(
                user, str(doc.get("name") or name or ""),
                content.replace(old_text, new_text),
                expected_version=int(doc.get("version") or 1))
            return ToolResult(
                text=(f"已编辑《{saved.get('name') or doc.get('name')}》"
                      f"（version={saved.get('version')}）"))
        except PlatformError as e:
            if getattr(e, "status_code", None) == 409:
                return ToolResult(
                    text="文档已被其他会话修改，请先 read_file 读取最新内容再重试",
                    is_error=True)
            return ToolResult(text=f"编辑失败：{e}", is_error=True)
        finally:
            platform.close()

    def effective_target_key(self, args: dict) -> str | None:
        """确认键作用域：优先文档 id，其次文档名。"""
        user = current_user_id()
        if args.get("id"):
            return f"doc:{user}:{args['id']}"
        name = args.get("name")
        if isinstance(name, str) and name.strip():
            return f"name:{user}:{name.strip().lower()}"
        return None
