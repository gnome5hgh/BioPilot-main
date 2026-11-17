"""RAGService 的构造工厂：每用户域单例的唯一组装点。

「RAGService 是单一实例」由本模块保证：检索与索引必须共享同一实例才能增量更新
（索引写进实例 A 的 BM25、检索却查实例 B 会读到陈旧数据）。按用户域缓存单例
（collection 加 ``_{user_id}`` 后缀、检索与索引天然按用户隔离），双重检查加锁，
并发下每用户只创建一次。

应用层服务（kb_service）与工具（rag_retrieve/index_status/view_image）都经
``get_rag_service`` 取实例——它们是消费方，不该自己组装组件图。
"""
from __future__ import annotations

import threading

from biopilot.config import BioPilotConfig
from biopilot.engine.rag.application.rag_service import RAGService

__all__ = ["get_rag_service"]

# ---------- 模块级服务缓存（按用户域一域一例） ----------
_rag_services: dict[str, RAGService] = {}
_rag_singleton_lock = threading.RLock()


def get_rag_service(config: BioPilotConfig | None = None,
                    user_id: str = "", db=None) -> RAGService:
    """按用户缓存的检索服务实例（增量更新与索引状态的前提）。

    Args:
        config: 可选配置对象，不传则使用 BioPilotConfig.from_env()。
        user_id: 归属用户（必填；工具侧经运行时上下文取当前 run 的归属）。
        db: 可选 MemoryDB；不传时首次读写索引状态才按配置懒建共享池。

    Returns:
        RAGService: 该用户唯一的检索服务实例。

    Raises:
        ValueError: user_id 为空。
    """
    if not user_id:
        raise ValueError("get_rag_service 缺少归属用户（user_id）")
    key = user_id
    with _rag_singleton_lock:
        svc = _rag_services.get(key)
        if svc is None:
            svc = RAGService(config or BioPilotConfig.from_env(),
                             user_id=key, db=db)
            _rag_services[key] = svc
        else:
            svc.bind_db(db)
    return svc
