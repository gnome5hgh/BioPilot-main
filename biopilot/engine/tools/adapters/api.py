"""tools 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块、``agents/`` 插件）一律经本文件、包根别名
或具体工具子模块使用 tools：Tool 契约与安全元数据、ToolResult 三通道、加载期
校验、运行时上下文（ContextVar）、工具装配与全部工具实现。

工具实现（``adapters/<组>/<工具>.py``）是模型 tool-call 的入向适配器——对外能力
的一部分；``spawn`` 例外：它反向依赖 agent 模块，为避免 import 环**不进本文件**，
消费方按叶子路径单独 import（如 ``agents/*/tools.py``）。
"""
from biopilot.engine.tools.constants import (
    SUMMARY_DECISION,
    SUMMARY_TERMINAL,
    SUMMARY_VIOLATIONS,
)
from biopilot.engine.tools.domain import Tool, ToolResult
from biopilot.engine.tools.application.offload import make_tool_result_offloader
from biopilot.engine.tools.application.roots import semantic_roots
from biopilot.engine.tools.application.runtime_context import (
    MemoryToolsContext,
    get_memory_context,
    get_rag_domain,
    reset_memory_context,
    reset_rag_domain,
    set_memory_context,
    set_rag_domain,
    current_user_id,
)
from biopilot.engine.tools.application.validation import validate_ref_args, validate_tool
from biopilot.engine.tools.application.assembly import make_tools
from biopilot.engine.tools.adapters.tool_result_store import make_tool_result_store
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
    "validate_ref_args",
    "make_tools",
    "make_tool_result_offloader",
    "make_tool_result_store",
    "semantic_roots",
    "MemoryToolsContext",
    "get_memory_context",
    "get_rag_domain",
    "reset_memory_context",
    "reset_rag_domain",
    "set_memory_context",
    "set_rag_domain",
    "current_user_id",
    "GlobTool",
    "GrepTool",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "DeleteFileTool",
    "ReadPdfTool",
    "ReadReferenceTool",
    "FormatCheckTool",
    "SubmitReviewTool",
    "FetchPdfTool",
    "SearchLiteratureTool",
]
