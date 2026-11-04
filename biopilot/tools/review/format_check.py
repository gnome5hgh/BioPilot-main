"""FormatCheckTool：笔记 Markdown 标题树与模板对比(review-agent 用,确定性代码)。

模板取自 review-agent 自己的 `references/paper_note.md`；待检查的笔记从平台按
id/名字读取，不再需要本地路径。
"""
from pathlib import Path

from biopilot.common.platform import PlatformError
from biopilot.engine.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class FormatCheckTool(Tool):
    """笔记 Markdown 标题树与模板对比(确定性代码,供 review-agent 用)。

    Attributes:
        name: str，工具名 "format_check"
        description: str，工具描述
        parameters: dict，JSON Schema（id/name）
        risk_level: str，"low"
        _template_path: str | None，模板路径（构造期由 agent 插件绑定）
    """

    name = "format_check"
    description = "检查平台文档的结构是否符合模板（对比 Markdown 标题树）"
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "file_id",
                   "description": "文档 id（与 name 二选一）"},
            "name": {"type": "string", "format": "file_name",
                     "description": "文档名（与 id 二选一）"},
        },
    }
    risk_level = "low"
    side_effects = ["read_file"]

    def __init__(self, template_path: str | Path | None = None):
        """初始化工具并绑定模板路径。

        Args:
            template_path: 模板文件路径（review-agent 的 tools.py 用 `__file__` 推导）。
        """
        super().__init__()
        self._template_path: str | None = str(template_path) if template_path else None

    def _template_file(self) -> Path | None:
        """返回模板文件路径；未绑定时返回 None。"""
        return Path(self._template_path) if self._template_path else None

    def _template_headings(self) -> list[str]:
        """读模板的标题树；模板不存在时返回空列表。"""
        tpl = self._template_file()
        if tpl is None or not tpl.exists():
            return []
        return [ln.lstrip("# ").strip()
                for ln in tpl.read_text(encoding="utf-8").splitlines()
                if ln.startswith("#")]

    def execute(self, id: str | None = None, name: str | None = None) -> ToolResult:
        """对比平台文档的标题树与模板。

        Args:
            id: 文档 id。
            name: 文档名。

        Returns:
            ToolResult，文本为缺失章节清单或「结构完整」；模板/文档取不到时返回错误文本。
        """
        headings = self._template_headings()
        if not headings:
            where = self._template_path or "本角色 references/paper_note.md"
            return ToolResult(is_error=True, text=f"模板不存在，无法比对结构：{where}")
        if not id and not name:
            return ToolResult(text="format_check 需要 id 或 name", is_error=True)
        user = current_user_id()
        platform = platform_for(self)
        try:
            doc = (platform.get_document(user, id) if id
                   else platform.get_document_by_name(user, name))
            content = str(doc.get("content") or "")
        except PlatformError as e:
            return ToolResult(text=f"读取文档失败：{e}", is_error=True)
        finally:
            platform.close()
        note_heads = [ln.lstrip("# ").strip()
                      for ln in content.splitlines() if ln.startswith("#")]
        missing = [h for h in headings if h not in note_heads]
        if missing:
            return ToolResult(text=f"缺少模板章节: {', '.join(missing)}")
        return ToolResult(text="结构完整，与模板一致")
