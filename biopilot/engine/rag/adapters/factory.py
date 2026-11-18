"""RAGService 的构造工厂：每用户域单例的唯一组装点。

「RAGService 是单一实例」由本模块保证：检索与索引必须共享同一实例才能增量更新
（索引写进实例 A 的 BM25、检索却查实例 B 会读到陈旧数据）。按用户域缓存单例
（collection 加 ``_{user_id}`` 后缀、检索与索引天然按用户隔离），双重检查加锁，
并发下每用户只创建一次。

应用层服务（kb_service）与工具（rag_retrieve/index_status/view_image）都经
``get_rag_service`` 取实例——它们是消费方，不该自己组装组件图。组件的构造细节
（嵌入/精排客户端、Milvus 连接与维度、状态库与降级、视觉描述器）全部收在
``build_components``：RAGService 只消费 ``RagComponents`` 的 provider 包。
"""
from __future__ import annotations

import logging
import threading

from biopilot.config import BioPilotConfig
from biopilot.engine.rag.adapters import components
from biopilot.engine.rag.adapters.index_state_store import (
    IndexStateStore, MemoryIndexStateStore,
)
from biopilot.engine.rag.application.rag_service import RAGService
from biopilot.engine.rag.domain.ports import RagComponents

__all__ = ["get_rag_service", "build_components"]

logger = logging.getLogger(__name__)

# ---------- 模块级服务缓存（按用户域一域一例） ----------
_rag_services: dict[str, RAGService] = {}
_rag_singleton_lock = threading.RLock()


def _make_state_store(config: BioPilotConfig, user_id: str, db):
    """构造索引状态存取器；库不可达时降级为进程内实现并告警。

    降级语义从应用层移到组装缝：状态只是增量优化的依据（不是真相源），索引
    本身仍可完成，代价是重启后全量重扫；真相链路（消息、记忆）有自己的启动
    预检，不靠这里兜底。

    Args:
        config: 全局配置（懒建共享池时取 ``runtime.memory_dsn``）。
        user_id: 归属用户（每用户一行状态）。
        db: 调用方持有的 MemoryDB；None 时按配置懒建。

    Returns:
        IndexStateStore 端口实现（MySQL 或进程内）。
    """
    try:
        real_db = db or components.default_db(config)
    except Exception as e:
        logger.warning(
            "索引状态库不可用，本次运行使用进程内状态（重启后会全量重扫）：%s", e)
        return MemoryIndexStateStore()
    return IndexStateStore(real_db, user_id)


class _ComponentPdfExtractor:
    """``PdfExtractor`` 端口的轻实现：调用点动态取 components 的抽取函数。

    动态取模块属性是刻意的——单测的桩（``stub_pdf_extract`` /
    ``stub_pdf_contents``）monkeypatch 的就是 ``components.extract_pdf``，
    动态取用才能让桩生效。
    """

    def extract(self, source: str, title: str = ""):
        """解析 PDF 文件路径。

        Args:
            source: PDF 绝对路径。
            title: 论文标题（来自平台表；绝不取文件名）。

        Returns:
            PdfText 解析产物。
        """
        return components.extract_pdf(source, title)

    def extract_bytes(self, data: bytes, title: str = "", *, digest: str = ""):
        """解析 PDF 字节（平台论文不落盘）。

        Args:
            data: PDF 字节。
            title: 论文标题。
            digest: 内容 sha256（解析缓存键）。

        Returns:
            PdfText 解析产物。
        """
        return components.extract_pdf_bytes(data, title, digest=digest)


def build_components(config: BioPilotConfig, user_id: str,
                     db=None) -> RagComponents:
    """按配置构造 RAG 组件的 provider 包（本模块对外唯一的组件组装入口）。

    Args:
        config: 全局配置。
        user_id: 归属用户（collection 后缀、状态行键）。
        db: 可选 MemoryDB（状态落库）；None 时 provider 首次访问才懒建共享池。

    Returns:
        RagComponents：全部字段为惰性 provider。
    """
    embedder_provider = lambda: components.build_embedder(config)  # noqa: E731
    return RagComponents(
        embedder=embedder_provider,
        reranker=lambda: components.build_reranker(config),
        # 维度由调用方传入（来自当前注入的编码器——测试可换假件；建集合时定死）。
        # 向量库构造在 provider 内，Milvus 未启动的 RuntimeError 原样上抛（软依赖语义）。
        vector_store=lambda dim: components.build_vector_store(config, user_id, dim),
        image_store=lambda: components.build_image_store(config),
        state_store=lambda: _make_state_store(config, user_id, db),
        pdf_extractor=lambda: _ComponentPdfExtractor(),
        figure_extractor=lambda: components.build_figure_extractor(),
        figure_describer=lambda: components.build_figure_describer(config),
        rewriter_llm=lambda: components.build_rewriter_llm(config),
    )


def get_rag_service(config: BioPilotConfig | None = None,
                    user_id: str = "", db=None) -> RAGService:
    """按用户缓存的检索服务实例（增量更新与索引状态的前提）。

    Args:
        config: 可选配置对象，不传则使用 BioPilotConfig.from_env()。
        user_id: 归属用户（必填；工具侧经运行时上下文取当前 run 的归属）。
        db: 可选 MemoryDB；不传时状态 provider 首次读写才按配置懒建共享池。
            复用已有实例且传入 db 时，进程内状态实现会升级为 MySQL。

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
            cfg = config or BioPilotConfig.from_env()
            svc = RAGService(cfg, user_id=key,
                             components=build_components(cfg, key, db))
            _rag_services[key] = svc
        elif db is not None:
            # 复用实例 + 调用方带现成池：进程内状态实现升级为 MySQL；
            # 已是 MySQL 实现就不动——换池没有收益，反而会丢正在使用的对象。
            store = svc.state_store
            if isinstance(store, MemoryIndexStateStore):
                svc.rebind_state_store(IndexStateStore(db, key))
    return svc
