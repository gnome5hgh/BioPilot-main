"""RAGService：整个检索栈的单一实例（索引与检索必须共享同一实例才能增量更新）。

索引器与检索器是同一个实例的两个视图。如果各自创建一套组件，写入时
更新的是实例 A 的索引，查询时用的却是实例 B 里陈旧的 BM25，导致新增
内容检索不到。整个检索与索引过程共用同一把可重入锁（含模型推理），
整段串行执行是最简单且正确的并发模型。
"""
import logging
import threading
import time

from biopilot.config import BioPilotConfig
from biopilot.engine.rag.domain import IndexOutcome, IndexStatus
from biopilot.engine.rag.parsers.chunker import AcademicChunker
from biopilot.engine.rag.services.breaker import RetrievalBreaker

logger = logging.getLogger(__name__)

#: Milvus 可连性探测结果的缓存秒数。带时限才跟得上外部服务的崩溃与恢复；
#: 探测本身要构造客户端并发 RPC，也不便宜，故不每次调用都探。
_MILVUS_PROBE_TTL = 30.0


class RAGService:
    """检索服务的外观：统一持有向量库、BM25、编码器、重排器、解析器等组件，全部惰性加载。

    每个组件经 _ensure_* 方法用「双重检查加锁」构造：先看缓存，为空才进锁
    再看一次，仍空才真正构造——保证并发下只初始化一次（模型加载耗时数秒，
    重复加载既慢又浪费）。索引器与检索器必须共享同一实例，见模块注释。

    Attributes:
        config: BioPilotConfig，全局配置（组件参数与路径的来源）
        lock: threading.RLock，保护整个索引/检索流程，保证并发状态一致
        chunker: AcademicChunker，构造期直接创建（纯逻辑无副作用）
        retrieval_breaker: RetrievalBreaker，检索熔断器（Milvus 不可达时跳闸）
        _embedder/_reranker/_vector_store/_milvus_available/_bm25/_indexer/_retriever/_rewriter: 惰性组件槽位（None 表示未构造，首次访问经双重检查加锁构造）
    """

    def __init__(self, config: BioPilotConfig, user_id: str, db=None):
        """初始化门面：先把所有组件槽位置空，首次访问才惰性构造。

        除 chunker（纯逻辑、构造无副作用）外，编码器/重排器/向量库/BM25 都走
        懒加载——既避免启动时加载数秒的模型，也让不碰检索的测试完全不会导入重依赖。

        Args:
            config: 全局配置对象，包含工作区路径、模型名等。
            user_id: 归属用户（必填）。每个用户派生独立 collection，论文不落
                本地文件——索引时由平台适配层取回字节、以 ``paper:<id>`` 作文档标识。
            db: MemoryDB 实例（索引状态落库）；None 时首次用状态才按
                ``runtime.memory_dsn`` 懒建共享连接池。

        Raises:
            ValueError: user_id 为空——引擎没有无用户的运行形态。
        """
        if not user_id:
            raise ValueError("RAGService 缺少归属用户（user_id）")
        self.user_id = user_id
        self.config = config
        self._db = db
        # 可重入锁，保护整个索引/检索流程，确保并发下状态一致
        self.lock = threading.RLock()

        # ---- 惰性加载的组件槽位 ----
        self._embedder = None          # 稠密向量编码器 (RagEmbedder)
        self._reranker = None          # 精排模型 (RagReranker)
        self._vector_store = None      # 向量库 (VectorStore)
        self._milvus_available = None    # Milvus 可连性探测缓存 (bool | None)
        self._milvus_checked_at = 0.0    # 上次探测时刻（time.monotonic），配合 TTL 失效
        self._bm25 = None              # BM25 索引 (Bm25Index)
        self._indexer = None           # 索引器视图 (RagIndexer)
        self._retriever = None         # 检索器视图 (Retriever)
        self._rewriter = None          # 改写器 (QueryRewriter)
        self._image_store = None       # 图表原图存取器 (ImageStore)
        self._state_store = None       # 索引状态存取器（MySQL / 进程内）

        # 纯逻辑组件，无副作用，直接构造。切块参数读配置（rag.chunker.*），
        # 配方哈希据此失效——改 YAML 即触发全量重索引。
        self.chunker = AcademicChunker(config.rag.chunker.max_tokens,
                                       config.rag.chunker.overlap_tokens)

        # 检索熔断器：Milvus 不可达时跳闸，省掉「每次检索都白等一轮连接超时」。
        # 每实例独立（实例按用户域构造）——故障域对齐故障源，一个用户的
        # collection 异常不再把所有用户的检索打入熔断。
        self.retrieval_breaker = RetrievalBreaker()

    # —— 惰性组件（双重检查加锁，保证并发下只初始化一次）——
    def _ensure_embedder(self):
        """惰性获取编码器：首次访问时构造并缓存。

        Returns:
            RagEmbedder: 云端编码器实例（构造不碰网络，失败在调用时暴露）。
        """
        # 双重检查加锁：先检查实例变量是否为空，为空则获取锁后再次检查，
        # 确保并发下只有一个线程执行构造，其余线程复用已构造的实例。
        if self._embedder is None:
            with self.lock:
                if self._embedder is None:
                    from biopilot.engine.rag.encoders.embedder import RagEmbedder
                    emb = self.config.rag.embedding
                    self._embedder = RagEmbedder(emb.base_url, emb.api_key,
                                                   emb.embed_model,
                                                   batch_size=emb.batch_size,
                                                   timeout=emb.timeout,
                                                   max_retries=emb.max_retries)
        return self._embedder

    def _ensure_reranker(self):
        """惰性获取重排模型：首次访问时构造并缓存。

        Returns:
            RagReranker: 云端重排器实例（构造不碰网络，失败在调用时暴露）。
        """
        if self._reranker is None:
            with self.lock:
                if self._reranker is None:
                    from biopilot.engine.rag.encoders.reranker import RagReranker
                    # 直接构造 config 的调用方（测试/嵌入宿主）未必经过 from_env 的继承回填，
                    # 故此处对空的端点/key 再兜底继承 embedding 一次。
                    rr = self.config.rag.rerank
                    emb = self.config.rag.embedding
                    self._reranker = RagReranker(rr.base_url or emb.base_url,
                                                   rr.api_key or emb.api_key,
                                                   rr.model,
                                                   timeout=rr.timeout,
                                                   max_retries=rr.max_retries)
        return self._reranker

    def _ensure_vector_store(self):
        """惰性获取向量库：首次访问时打开（必要时创建）。

        维度从 embedder 读取（建集合时定死）；uri 来自配置（本地文件→Lite、
        http→Standalone）。连接失败抛带可行动指引的错——Milvus 是服务而非
        本地文件，可能未启动，不能假设向量库永不宕机。

        Returns:
            VectorStore: 向量库实例。

        Raises:
            RuntimeError: Milvus 未连接（附 `docker compose up -d` 指引）。
        """
        if self._vector_store is None:
            with self.lock:
                if self._vector_store is None:
                    from biopilot.engine.rag.storage.vector_store import VectorStore
                    dim = self._ensure_embedder().dim
                    try:
                        self._vector_store = VectorStore(
                            self.config.rag.storage.uri, dim,
                            collection_name=(
                                self.config.rag.storage.collection
                                + f"_{self.user_id}"),
                            batch_size=self.config.rag.storage.batch_size,
                            read_timeout=self.config.rag.storage.timeout,
                            write_timeout=self.config.rag.storage.write_timeout,
                        )
                    except Exception as e:
                        raise RuntimeError(
                            f"Milvus 未连接（{self.config.rag.storage.uri}）：{e}。"
                            "请运行 `docker compose up -d` 启动服务后重试。"
                        ) from e
        return self._vector_store

    def milvus_available(self, ttl: float = _MILVUS_PROBE_TTL) -> bool:
        """探测 Milvus 是否可连接，结果缓存 ttl 秒。

        Lite（本地文件 uri）恒可连；Standalone 未启动则 False。缓存带时限是必需的——
        Milvus 是外部服务，中途崩溃与恢复都可能发生，永久缓存会让探测结果与实际状态长期
        背离。检索路径的实时保护不靠本方法（它要构造客户端并发 RPC，放热路径太贵），
        而由 `retrieval_breaker` 负责：那是以真实检索当探测，比这里更准。

        Args:
            ttl: float，探测结果的有效秒数，过期即重新探测。

        Returns:
            bool: True 表示可连接。
        """
        now = time.monotonic()
        if self._milvus_available is None or now - self._milvus_checked_at >= ttl:
            try:
                self._ensure_vector_store()
                self._milvus_available = True
            except RuntimeError:
                self._milvus_available = False
            self._milvus_checked_at = now
        return self._milvus_available

    def _ensure_bm25(self):
        """惰性获取 BM25 索引：首次访问时创建。

        Returns:
            Bm25Index: BM25 索引实例。
        """
        # Bm25Index 是纯内存结构，无持久化，进程重启后需从向量库重建。
        # 这里只创建空索引；填充有两条路径——检索器首次查询时的进程级恢复
        # （retriever.py，裸 rebuild 自向量库）与索引器的增量/全量写入。
        if self._bm25 is None:
            with self.lock:
                if self._bm25 is None:
                    from biopilot.engine.rag.encoders.bm25 import Bm25Index
                    self._bm25 = Bm25Index()
        return self._bm25

    def extract_figures(self, source: str | bytes):
        """定位一篇 PDF 里的图与表区域（媒体块构造用），不渲染图像。

        这是 `rag → vision` 的唯一一条边，且**惰性 import**：vision 有自己的
        重型依赖（PyMuPDF 版面管线、pdffigures2 式检测），包导入期拉起它会拖慢
        每一次 import biopilot.engine.rag 的调用方。

        Args:
            source: PDF 文件绝对路径，或 PDF 字节（平台论文不落盘）。

        Returns:
            list[Figure]: 检测到的图与表区域；检测不出（扫描件/纯图）为空列表。
        """
        from biopilot.engine.vision import FigureExtractor
        return FigureExtractor().extract(source, render_images=False)

    def render_figures(self, source: str | bytes, figures) -> None:
        """只渲染给定的这批图表区域（就地把图像字节填进这些对象）。

        索引侧先 `extract_figures` 定位，再只渲染最终会入库的那批——整篇渲染会为
        一堆不产块的区域白栅格化。

        Args:
            source: PDF 文件绝对路径，或 PDF 字节（平台论文不落盘）。
            figures: 要渲染的 Figure 列表（就地修改）。
        """
        from biopilot.engine.vision import FigureExtractor
        FigureExtractor().render(source, figures)

    @property
    def image_store(self):
        """图表原图的存取器（惰性单例；关掉开关时是空实现）。

        Returns:
            ImageStore: 存取器。
        """
        if self._image_store is None:
            from biopilot.engine.rag.storage import make_image_store
            self._image_store = make_image_store(self.config)
        return self._image_store

    @property
    def state_store(self):
        """索引状态存取器（惰性单例）。

        状态落在 MySQL：每个用户域一行。连接池优先用构造时注入的，未注入时按
        ``runtime.memory_dsn`` 懒建共享池。库不可达时退回进程内实现并告警：状态
        只是增量优化的依据（不是真相源），索引本身仍可完成，代价是重启后全量重扫；
        真相链路（消息、记忆）有自己的启动预检，不靠这里兜底。

        Returns:
            索引状态存取器（``IndexStateStore`` 或 ``MemoryIndexStateStore``）。
        """
        if self._state_store is None:
            with self.lock:
                if self._state_store is None:
                    from biopilot.engine.rag.storage.index_state_store import (
                        IndexStateStore, MemoryIndexStateStore,
                    )
                    try:
                        db = self._db or _default_db(self.config)
                    except Exception as e:
                        logger.warning(
                            "索引状态库不可用，本次运行使用进程内状态"
                            "（重启后会全量重扫）：%s", e)
                        self._state_store = MemoryIndexStateStore()
                    else:
                        self._state_store = IndexStateStore(db, self.user_id)
        return self._state_store

    def bind_db(self, db) -> None:
        """补挂索引状态连接池（首次构造没传、之后的调用方有现成池时）。

        进程内实现会就地换成 MySQL 实现；已经是 MySQL 实现就不动——它连着同一个
        库，换池没有收益，反而会丢掉正在使用的对象。

        Args:
            db: MemoryDB 实例；None 表示不做任何事。
        """
        if db is None:
            return
        self._db = db
        if self._state_store is None:
            return
        from biopilot.engine.rag.storage.index_state_store import (
            IndexStateStore, MemoryIndexStateStore,
        )
        if isinstance(self._state_store, MemoryIndexStateStore):
            self._state_store = IndexStateStore(db, self.user_id)

    # ---------- 索引器/检索器视图（延迟创建） ----------
    def get_indexer(self):
        """惰性创建并返回索引器视图。

        索引器 indexer 和检索器 retriever 共享同一个 RAGService 实例，因此共享所有底层组件。

        Returns:
            RagIndexer: 索引器实例。
        """
        if self._indexer is None:
            # 使用函数内导入避免模块循环依赖
            from biopilot.engine.rag.services.indexer import RagIndexer
            self._indexer = RagIndexer(self)
        return self._indexer

    def get_retriever(self):
        """惰性创建并返回检索器视图。

        Returns:
            Retriever: 检索器实例。
        """
        if self._retriever is None:
            from biopilot.engine.rag.services.retriever import Retriever
            self._retriever = Retriever(self)
        return self._retriever

    def get_rewriter(self):
        """惰性创建并返回 query 改写器（RAG 包内首个 LLM 调用点）。

        连接参数取 config.rag.query_rewrite 三元组，以主 LLM 为基底逐项覆盖：
        base_url/api_key 留空（from_env 已继承主 LLM，此处再兜底）沿用主配置，
        model 留空沿用主模型（历史默认行为）。LLMClient 对空 api_key fail-fast
        ——调用方（RagRetrieveTool）catch 后降级原 query。

        Returns:
            QueryRewriter: 改写器实例（进程内缓存）。
        """
        if self._rewriter is None:
            from dataclasses import replace

            from biopilot.engine.llm.services.client import LLMClient
            from biopilot.engine.rag.services.query_rewriter import QueryRewriter
            # 以主 LLM 配置为基底，query_rewrite 三元组逐项覆盖（空值回退主配置）。
            # 直接构造 config 的调用方（测试/嵌入宿主）未必经过 from_env 的继承回填，
            # 故此处对空值再兜底一次。
            qr = self.config.rag.query_rewrite
            llm_cfg = replace(
                self.config.llm,
                base_url=qr.base_url or self.config.llm.base_url,
                api_key=qr.api_key or self.config.llm.api_key,
                model=qr.model or self.config.llm.model,
            )
            self._rewriter = QueryRewriter(
                LLMClient(llm_cfg),
                history_limit=self.config.rag.query_rewrite.history_messages,
                rewrite_num=self.config.rag.query_rewrite.rewrite_num,
                max_queries=self.config.rag.query_rewrite.max_queries,
                max_query_chars=self.config.rag.query_rewrite.max_query_chars)
        return self._rewriter

    # ---------- 对外便捷入口（索引/检索持同一把锁） ----------
    def index_document_bytes(self, data: bytes, doc_key: str,
                             title: str | None = None) -> IndexOutcome:
        """把一篇平台论文（内存字节）索引进向量库（持锁）。

        论文原文来自平台内部接口，不落本地文件；文档身份用 ``paper:<paper_id>``
        （见 ``paper_doc_key``）。块 id 由文档标识派生，同一篇论文重复索引仍是
        「先删后建」的幂等覆盖。

        Args:
            data: PDF 字节。
            doc_key: 文档标识（``paper:<paper_id>``）。
            title: 论文标题（来自平台表）。

        Returns:
            IndexOutcome，本次入库的状态、块数与原因。
        """
        with self.lock:
            return self.get_indexer().index_document_bytes(
                data, doc_key, title=title)

    def index_status(self) -> IndexStatus:
        """索引体检快照（持锁，只读）。

        与索引写入共用同一把锁：体检要读状态文件与向量库，不持锁会读到写一半的中间态。

        Returns:
            IndexStatus，状态文件 / 向量库 / 关键词索引 / 语料根的对照结果。
        """
        with self.lock:
            return self.get_indexer().status()

    def retrieve(self, query: str, top_k: int | None = None):
        """检索入口（持锁），返回按相关度排序的块列表。

        Args:
            query: 检索查询文本。
            top_k: 需要返回的结果块数；None 时取配置 ``rag.retriever.top_k``
                （默认值单点在 config，不再用模块常量字面量）。

        Returns:
            list[Chunk]: 按相关度降序排列的 Chunk 对象列表。
        """
        if top_k is None:
            top_k = self.config.rag.retriever.top_k
        with self.lock:
            return self.get_retriever().retrieve(query, top_k)

    def retrieve_scored(self, query: str, top_k: int | None = None):
        """检索入口（持锁），返回 (块, RRF 融合分) 有序对。

        知识库的「试检索」需要把排序依据展示给用户；与 retrieve 共用同一段
        检索实现，不会出现两个出口结果不一致。

        Args:
            query: 检索查询文本。
            top_k: 需要返回的结果块数；None 时取配置默认值。

        Returns:
            list[tuple[Chunk, float]]: 按相关度降序排列的块与融合分。
        """
        if top_k is None:
            top_k = self.config.rag.retriever.top_k
        with self.lock:
            return self.get_retriever().retrieve_scored(query, top_k)

    def list_document_chunks(self, doc_key: str):
        """列出某篇文档当前索引里的全部块（持锁，只读）。

        Args:
            doc_key: 文档标识：本地语料是绝对路径，平台论文是 ``paper:<id>``。

        Returns:
            list[Chunk]: 该文档的块列表；文档不在索引里时为空列表。
        """
        with self.lock:
            store = self._ensure_vector_store()
            return [chunk for chunk, _mtime in store.all_documents()
                    if chunk.path == str(doc_key)]

    def document_chunk_counts(self) -> dict[str, int]:
        """按文档路径统计向量库块数（持锁，只读）。

        MySQL 的 `bio_file`（勾选真相）与 `bio_rag_paper_status`（索引状态）是知识库的真相；这里返回向量库
        实际持有的块数，供对账发现「库里多/少/缺」并触发重建或清理。

        Returns:
            dict[str, int]: 文档绝对路径 → 块数。
        """
        with self.lock:
            return self._ensure_vector_store().document_chunk_counts()

    def remove_document(self, doc_key: str) -> bool:
        """把一篇文档从索引里整体移除（持锁）。

        用于「移出知识库但保留文件」：只删该文档的块、BM25 行与图表对象，
        不动平台论文行与 OSS 原文。

        Args:
            doc_key: 文档标识：本地绝对路径或 ``paper:<paper_id>``。

        Returns:
            bool: 执行了移除时为 True。
        """
        with self.lock:
            return self.get_indexer().remove_document(doc_key)


# ---------- 模块级服务缓存（按用户域一域一例） ----------
_rag_services: dict[str, RAGService] = {}
_rag_singleton_lock = threading.RLock()

#: 索引状态默认连接池（按首个调用方的 DSN 懒建；生产只有一个库）
_default_db_instance = None
_default_db_lock = threading.Lock()


def _default_db(config: BioPilotConfig):
    """按配置懒建共享的 MemoryDB（调用方未注入连接池时用）。

    DSN 优先级：环境变量 ``BIOPILOT_MEMORY_MYSQL_DSN``（启动脚本与容器都会设置，
    也是适配层其他 SQL 用的那一条）→ ``runtime.memory_dsn``。优先环境变量是为了
    让「同一进程里的库」只有一个口径，避免配置默认值把状态写进另一个库。

    Args:
        config: 全局配置（取 ``runtime.memory_dsn``）。

    Returns:
        MemoryDB: 进程内共享的连接池。
    """
    global _default_db_instance
    if _default_db_instance is None:
        with _default_db_lock:
            if _default_db_instance is None:
                import os

                from biopilot.engine.memory.storage.database import MemoryDB
                dsn = (os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN")
                       or config.runtime.memory_dsn)
                _default_db_instance = MemoryDB(dsn)
    return _default_db_instance


def get_rag_service(config: BioPilotConfig | None = None,
                    user_id: str = "", db=None) -> RAGService:
    """按用户缓存的检索服务实例（增量更新与索引状态的前提）。

    每用户一个实例——collection 加 `_{用户}` 后缀、检索与索引天然按用户隔离。
    双重检查加锁，保证并发下每用户只创建一次。

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
