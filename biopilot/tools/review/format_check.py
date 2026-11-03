"""FormatCheckTool：笔记 Markdown 标题树与模板对比(review-agent 用,确定性代码)。

模板取自 **review-agent 自己的 `references/paper_note.md`**——审查方的标准就是它手里那份，
与审查流程里 `read_reference` 读到的是同一个文件。刻意不读 note-agent 的那份：
工具按 A 判定、审查方按 B 判定时，同一篇笔记会同时得到「结构完整」和「缺章节」，
这比模板缺失更难查。

模板路径在构造期由 `agents/review-agent/tools.py` 绑定（`__file__` 推导），
运行期不再查找、不依赖部署路径。模板缺失时**返回明确错误、绝不落盘**。
"""
from pathlib import Path

from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.constants import ScopeRoot


class FormatCheckTool(Tool):
    """笔记 Markdown 标题树与模板对比(确定性代码,供 review-agent 用)。

    Attributes:
        name: str，工具名 "format_check"
        description: str，工具描述
        parameters: dict，JSON Schema（path）
        risk_level: str，"low"
        root_hints: list[str]，笔记根与草稿根
        _template_path: str | None，模板路径（构造期由 agent 插件绑定；测试可覆盖）
    """

    name = "format_check"
    description = "检查笔记结构是否符合模板（对比 Markdown 标题树）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "format": "path", "description": "笔记绝对路径"},
        },
        "required": ["path"],
    }
    risk_level = "low"
    root_hints = [ScopeRoot.NOTE, ScopeRoot.SCRATCH]
    #: 两侧都只读：读笔记与读模板比结构，不写任何落点
    side_effects = ["read_file"]

    def __init__(self, template_path: str | Path | None = None):
        """初始化工具并绑定模板路径。

        Args:
            template_path: 模板文件路径（review-agent 的 tools.py 用 `__file__` 推导；
                测试可显式传入）。
        """
        super().__init__()
        self._template_path: str | None = str(template_path) if template_path else None

    def _template_file(self) -> Path | None:
        """返回模板文件路径；未绑定时返回 None。"""
        return Path(self._template_path) if self._template_path else None

    def _template_headings(self) -> list[str]:
        """读模板的标题树；模板不存在时返回空列表，由调用方转成明确错误（不落盘）。"""
        tpl = self._template_file()
        if tpl is None or not tpl.exists():
            return []
        return [ln.lstrip("# ").strip()
                for ln in tpl.read_text(encoding="utf-8").splitlines() if ln.startswith("#")]

    def execute(self, path: str) -> ToolResult:
        """对比笔记标题树与模板,返回缺失章节清单或"结构完整"。

        Args:
            path: str，待检查笔记的绝对路径

        Returns:
            ToolResult，文本为缺失章节清单或「结构完整」；模板取不到时返回错误文本
            （不落盘、不中断调用方流程）。
        """
        headings = self._template_headings()
        if not headings:
            where = self._template_path or "本角色 references/paper_note.md"
            return ToolResult(is_error=True, text=f"模板不存在，无法比对结构：{where}")
        note_heads = [ln.lstrip("# ").strip()
                      for ln in Path(path).read_text(encoding="utf-8").splitlines()
                      if ln.startswith("#")]
        missing = [h for h in headings if h not in note_heads]
        if missing:
            return ToolResult(text=f"缺少模板章节: {', '.join(missing)}")
        return ToolResult(text="结构完整，与模板一致")
