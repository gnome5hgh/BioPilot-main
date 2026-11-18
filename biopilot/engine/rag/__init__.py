"""RAG 检索栈。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：检索服务与
每用户单例工厂、试检索、分块读取、索引状态操作、向量清理、文档标识词汇。
分层：domain（实体/DTO/端口）→ application（门面/索引器/检索器/分块/BM25）
→ adapters（向量库/对象存储/编码器/精排/PDF/状态库 + 公开契约）。
"""
from biopilot.engine.rag.adapters.api import *  # noqa: F401,F403
from biopilot.engine.rag.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
