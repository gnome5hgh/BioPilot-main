"""engine.tools —— 工具域包：Tool 契约（domain）+ 工具运行时（application）+ 工具实现（adapters）。

三层职责：

- ``domain/``：Tool ABC 与安全元数据、ToolResult 三通道载体——模型可调用能力的契约词汇
- ``application/``：加载期校验、runtime_context（ContextVar 运行时绑定）、大结果外置、
  语义根派生与 ``make_tools`` 工具装配
- ``adapters/``：具体工具实现（file/code/search/rag/recall/review/docs/skills/vision/
  orchestration，模型的 tool-call 执行入口）与大工具结果的对象存储外置（tool_result_store）

包根只再导出契约与最常用原子工具，方便测试与装配方统一导入；rag / recall / vision /
code / docs / skills / orchestration 等工具从各自子包导入。跨层共享的常量/工具函数在
`biopilot.common` 与 `biopilot.engine.tools.constants`，不要放回包根。
"""
from biopilot.engine.tools.constants import (
    SUMMARY_DECISION,
    SUMMARY_TERMINAL,
    SUMMARY_VIOLATIONS,
)
from biopilot.engine.tools.domain import Tool, ToolResult
from biopilot.engine.tools.application.validation import validate_tool
from biopilot.engine.tools.adapters.file.glob import GlobTool
from biopilot.engine.tools.adapters.file.grep import GrepTool
from biopilot.engine.tools.adapters.file.read_file import ReadFileTool
from biopilot.engine.tools.adapters.file.write_file import WriteFileTool
from biopilot.engine.tools.adapters.file.edit_file import EditFileTool
from biopilot.engine.tools.adapters.file.delete_file import DeleteFileTool
from biopilot.engine.tools.adapters.file.read_pdf import ReadPdfTool
from biopilot.engine.tools.adapters.file.read_reference import ReadReferenceTool
from biopilot.engine.tools.adapters.review.format_check import FormatCheckTool
from biopilot.engine.tools.adapters.review.submit_review import SubmitReviewTool
from biopilot.engine.tools.adapters.search.fetch_pdf import FetchPdfTool
from biopilot.engine.tools.adapters.search.search_literature import SearchLiteratureTool

__all__ = [
    "SUMMARY_DECISION",
    "SUMMARY_TERMINAL",
    "SUMMARY_VIOLATIONS",
    "Tool",
    "ToolResult",
    "validate_tool",
    "GlobTool", "GrepTool", "ReadFileTool", "WriteFileTool", "EditFileTool",
    "DeleteFileTool", "ReadPdfTool", "ReadReferenceTool", "FormatCheckTool",
    "SubmitReviewTool", "FetchPdfTool", "SearchLiteratureTool",
]
