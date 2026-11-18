"""rag 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块）一律经本文件或包根别名使用 rag：
检索服务（``RAGService`` / ``get_rag_service``）、试检索、分块读取、索引状态
操作、向量清理与文档标识词汇。出向实现（嵌入/精排/Milvus/MinIO/PDF/状态库）
同住 ``adapters/``，同属公开面。
"""
from biopilot.engine.rag.adapters.components import (
    build_embedder, build_figure_extractor, build_figure_describer,
    build_image_store, build_rewriter_llm, build_reranker, build_vector_store,
)
from biopilot.engine.rag.adapters.factory import build_components, get_rag_service
from biopilot.engine.rag.adapters.index_state_store import list_domain_states
from biopilot.engine.rag.adapters.paper_status import (
    apply_results, delete_by_user, delete_index_state_by_user, mark_indexing,
    normalize, requeue, requeue_all, select_all_papers, select_for_reconcile,
    select_paper_states, select_papers_for_index, select_users_with_kb,
    select_users_with_orphan_rows,
)
from biopilot.engine.rag.adapters.vector_store import purge_user_vectors
from biopilot.engine.rag.application.rag_service import RAGService
from biopilot.engine.rag.constants import IndexOutcomeStatus, paper_doc_key, paper_id_of
from biopilot.engine.rag.domain import Block, Chunk, PdfText, Section, section_label

__all__ = [
    "RAGService", "get_rag_service", "build_components",
    "build_embedder", "build_reranker", "build_vector_store", "build_image_store",
    "build_figure_extractor", "build_figure_describer", "build_rewriter_llm",
    "list_domain_states",
    "apply_results", "delete_by_user", "delete_index_state_by_user", "mark_indexing",
    "normalize", "requeue", "requeue_all", "select_all_papers", "select_for_reconcile",
    "select_paper_states", "select_papers_for_index", "select_users_with_kb",
    "select_users_with_orphan_rows",
    "purge_user_vectors",
    "IndexOutcomeStatus", "paper_doc_key", "paper_id_of", "section_label",
    "Block", "Chunk", "PdfText", "Section",
]


def build_rag(config, user_id: str, db=None) -> RAGService:
    """按用户构造一个独立的 RAGService 实例（不经每用户单例缓存）。

    供测试与需要隔离实例的场景；生产路径一律走 ``get_rag_service``。

    Args:
        config: 全局配置。
        user_id: 归属用户。
        db: 可选 MemoryDB（状态落库）。

    Returns:
        RAGService。
    """
    return RAGService(config, user_id=user_id,
                      components=build_components(config, user_id, db))
