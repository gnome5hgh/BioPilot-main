"""biopilot RAG 检索子系统：文档解析、向量/稀疏索引与混合检索。

对外统一导出解析器、服务门面与检索工具；领域模型从 `domain/`、编码器与向量存储
等底层组件经由各自子包访问（`adapters/` 下稠密/精排与向量库、`application/bm25.py` 稀疏）。重依赖（pymilvus、
jieba、rank_bm25）由 RAGService 内部惰性加载，包导入本身不拉取，避免拖慢应用与
测试启动。
"""
from biopilot.engine.rag.domain import Block, Chunk, PdfText, Section
from biopilot.engine.rag.application.chunker import AcademicChunker
from biopilot.engine.rag.application.rag_service import RAGService
from biopilot.engine.rag.adapters.factory import get_rag_service
from biopilot.engine.rag.application.indexer import RagIndexer
from biopilot.engine.rag.application.retriever import Retriever

__all__ = ["AcademicChunker", "Chunk", "Section", "PdfText", "Block",
           "RAGService", "get_rag_service", "RagIndexer", "Retriever"]
