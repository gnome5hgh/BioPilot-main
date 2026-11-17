"""RAG 域适配器的构造工厂（组装根在 rag 域的延伸）。

RAGService（应用层）不再自行构造任何适配器：编码器/重排器/向量库/对象存储/
图表提取器/改写器 LLM 的构造全部收口到本模块，由 rag_service 经「惰性 builder
调用」消费——双重检查加锁与懒加载语义原样保留，只是构造动作换了落点。

本模块是应用层 → 适配器 import 的**登记白名单**（架构守护测试的三层边界规则）：它
import 客户端库依赖的适配器模块，但自身不做任何编排判断，只负责按配置把具体类造出来。
"""
from __future__ import annotations

from dataclasses import replace

from biopilot.engine.rag.adapters.embedder import RagEmbedder
from biopilot.engine.rag.adapters.reranker import RagReranker
from biopilot.engine.rag.adapters.vector_store import VectorStore
from biopilot.engine.rag.adapters.pdf_extract import extract_pdf, extract_pdf_bytes

__all__ = [
    "build_embedder", "build_reranker", "build_vector_store", "build_image_store",
    "build_figure_extractor", "build_rewriter_llm", "default_db",
    "extract_pdf", "extract_pdf_bytes",
]


def default_db(config):
    """按配置取共享的 MemoryDB 连接池（索引状态落库用）。

    DSN 优先级：环境变量 ``BIOPILOT_MEMORY_MYSQL_DSN``（启动脚本与容器都会设置，
    也是适配层其他 SQL 用的那一条）→ ``runtime.memory_dsn``。优先环境变量是为了
    让「同一进程里的库」只有一个口径，避免配置默认值把状态写进另一个库。

    Args:
        config: 全局配置（取 ``runtime.memory_dsn``）。

    Returns:
        MemoryDB: 进程内共享的连接池。
    """
    import os

    from biopilot.engine.memory.adapters.database import MemoryDB

    dsn = (os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN")
           or config.runtime.memory_dsn)
    return MemoryDB(dsn)


def build_embedder(config):
    """按配置构造稠密编码器（构造不碰网络，失败在调用时暴露）。

    Args:
        config: BioPilotConfig，取 ``rag.embedding`` 段。

    Returns:
        RagEmbedder：云端编码器实例。
    """
    emb = config.rag.embedding
    return RagEmbedder(emb.base_url, emb.api_key,
                       emb.embed_model,
                       batch_size=emb.batch_size,
                       timeout=emb.timeout,
                       max_retries=emb.max_retries)


def build_reranker(config):
    """按配置构造精排器（构造不碰网络，失败在调用时暴露）。

    Args:
        config: BioPilotConfig，取 ``rag.rerank`` 段（空端点/key 兜底继承 embedding）。

    Returns:
        RagReranker：云端精排器实例。
    """
    # 直接构造 config 的调用方（测试/嵌入宿主）未必经过 from_env 的继承回填，
    # 故此处对空的端点/key 再兜底继承 embedding 一次。
    rr = config.rag.rerank
    emb = config.rag.embedding
    return RagReranker(rr.base_url or emb.base_url,
                       rr.api_key or emb.api_key,
                       rr.model,
                       timeout=rr.timeout,
                       max_retries=rr.max_retries)


def build_vector_store(config, user_id: str, dim: int) -> VectorStore:
    """按配置构造向量库（collection 加用户后缀，维度由编码器定死）。

    Args:
        config: BioPilotConfig，取 ``rag.storage`` 段。
        user_id: 归属用户（collection 后缀，多用户隔离）。
        dim: 向量维度（来自编码器）。

    Returns:
        VectorStore：向量库实例（Lite/Standalone 双模）。
    """
    return VectorStore(
        config.rag.storage.uri, dim,
        collection_name=(config.rag.storage.collection + f"_{user_id}"),
        batch_size=config.rag.storage.batch_size,
        read_timeout=config.rag.storage.timeout,
        write_timeout=config.rag.storage.write_timeout,
    )


def build_image_store(config):
    """按配置构造图表原图存取器（``rag.store_images`` 关闭时空实现）。

    经模块属性动态调用 ``make_image_store``：单测的 autouse 桩
    （``_no_object_store``）monkeypatch 的是 image_store 模块属性，动态取用
    才能让桩生效。

    Args:
        config: BioPilotConfig。

    Returns:
        ImageStore：对象存储实现或空实现。
    """
    from biopilot.engine.rag.adapters import image_store as image_store_mod
    return image_store_mod.make_image_store(config)


def build_figure_extractor():
    """构造图表提取器（vision 域的无状态实例，每次新建）。

    Returns:
        FigureExtractor：PDF 图表提取器。
    """
    from biopilot.engine.vision import FigureExtractor
    return FigureExtractor()


def build_rewriter_llm(config):
    """按配置构造 query 改写专用的 LLM 客户端。

    连接参数取 ``rag.query_rewrite`` 三元组，以主 LLM 为基底逐项覆盖：
    base_url/api_key 留空（from_env 已继承主 LLM，此处再兜底）沿用主配置，
    model 留空沿用主模型（历史默认行为）。LLMClient 对空 api_key fail-fast
    ——调用方（RagRetrieveTool）catch 后降级原 query。

    Args:
        config: BioPilotConfig。

    Returns:
        LLMClient：改写器专用客户端。
    """
    from biopilot.engine.llm.adapters.client import LLMClient

    # 以主 LLM 配置为基底，query_rewrite 三元组逐项覆盖（空值回退主配置）。
    # 直接构造 config 的调用方（测试/嵌入宿主）未必经过 from_env 的继承回填，
    # 故此处对空值再兜底一次。
    qr = config.rag.query_rewrite
    llm_cfg = replace(
        config.llm,
        base_url=qr.base_url or config.llm.base_url,
        api_key=qr.api_key or config.llm.api_key,
        model=qr.model or config.llm.model,
    )
    return LLMClient(llm_cfg)
