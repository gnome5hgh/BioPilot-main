"""review-agent 的工具装配：两类审查的共用工具并集。

两类审查流程已内置在本角色 AGENT.md 里（笔记审查 / 选题产物审查），共用同一工具并集；
模板经 read_reference 从本角色 references/ 读取，format_check 绑定同一份模板文件。
"""
from pathlib import Path

from biopilot.config import BioPilotConfig
from biopilot.tools.services.assembly import make_tools
from biopilot.tools import (
    ReadFileTool, ReadPdfTool, FormatCheckTool, SubmitReviewTool, GlobTool, GrepTool,
    ReadReferenceTool,
)
from biopilot.tools.recall import get_recall_tools

_REFERENCES = Path(__file__).resolve().parent / "references"

TOOLS = make_tools(BioPilotConfig.from_env(), [
    ReadFileTool, ReadPdfTool,
    ReadReferenceTool(_REFERENCES),
    FormatCheckTool(template_path=_REFERENCES / "paper_note.md"),
    SubmitReviewTool, GlobTool, GrepTool,
]) + get_recall_tools()
# 叶子角色（allowed_spawns: []）：不装 spawn 工具——框架会拒绝，工具只会误导模型。
