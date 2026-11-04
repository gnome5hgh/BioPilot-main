"""RAG 层间数据载体（dto）。

把数据从一层搬到另一层的对象：解析产物（PdfText / Block）、索引结果
（IndexOutcome / IndexStatus）、查询改写结果（RewriteResult）。
与 `entity/` 的分界是「是不是 RAG 业务里的东西本身」——这里只回答「数据长什么样」。
"""
from biopilot.engine.rag.domain.dto.block import Block
from biopilot.engine.rag.domain.dto.index_outcome import IndexOutcome
from biopilot.engine.rag.domain.dto.index_status import IndexStatus
from biopilot.engine.rag.domain.dto.pdf_text import PdfText
from biopilot.engine.rag.domain.dto.rewrite_result import RewriteResult

__all__ = [
    "Block",
    "PdfText",
    "IndexOutcome",
    "IndexStatus",
    "RewriteResult",
]
