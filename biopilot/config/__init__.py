# biopilot/config/__init__.py
"""
全局配置模块，提供 LLM 连接参数和项目运行时配置。

配置加载优先级（从低到高）：
    1. dataclass 默认值（`sections.py` 是所有可调参数值的**唯一声明点**——改默认值只改那里）
    2. MySQL 的 ``bio_config``（设置页写入的稀疏覆盖，只存改过的路径）
    3. config.yaml 里仅剩的引导层（连接串/外部地址/本机路径）
    4. 环境变量（最高优先级，按 ``BIOPILOT_`` + 配置路径大写派生）

测试与离线脚本可用 ``BIOPILOT_CONFIG_SOURCE=file`` 跳过数据库，回到
「默认值 → YAML → env」的文件链路。

配置树与设置页的字段描述同构：
``runtime`` / ``corpus`` / ``intent`` / ``rag{embedding, rerank,
retriever, query_rewrite, chunker, storage, tools}`` / ``memory`` /
``agents{timeouts}`` / ``security`` / ``compaction``，外加保留的顶层
``llm`` / ``vision``；平台后端连接在 ``platform`` 段。

env 名约定：字段路径以 ``_`` 连接并大写，前缀 ``BIOPILOT_``。例如
``rag.storage.uri`` → ``BIOPILOT_RAG_STORAGE_URI``，
``rag.query_rewrite.model`` → ``BIOPILOT_RAG_QUERY_REWRITE_MODEL``。无例外表；
``agents.timeouts`` 是自由 dict，不派生 env（通过设置页的 JSON 编辑器维护）。

使用方式::

    config = BioPilotConfig.from_env()          # 自动加载（引擎入口会读数据库）
    config = BioPilotConfig.from_env("my.yaml") # 指定 YAML 路径（文件模式）

包内按角色平铺：``sections.py``（配置分区 dataclass 树）+ ``settings.py``
（合并与派生）+ ``schema.py``（设置页字段描述与校验）+ ``store.py``（MySQL
持久化/加密/历史）；本文件只做再导出，消费方一律
``from biopilot.config import ...``。
"""
from biopilot.config.settings import (
    BioPilotConfig,
    db_source_enabled,
    enable_db_source,
    ensure_legacy_import,
    user_cache_root,
)
from biopilot.config.sections import (
    AgentsConfig,
    ChunkerConfig,
    CorpusConfig,
    EmbeddingConfig,
    IntentConfig,
    IntentJevConfig,
    ClassifierConfig,
    SecurityConfig,
    LLMConfig,
    MemoryConfig,
    PlatformConfig,
    QueryRewriteConfig,
    RagConfig,
    RagToolsConfig,
    RerankConfig,
    RetrieverConfig,
    RuntimeConfig,
    MinioConfig,
    StorageConfig,
    VisionLLMConfig,
)

__all__ = [
    "BioPilotConfig",
    "db_source_enabled",
    "enable_db_source",
    "ensure_legacy_import",
    "user_cache_root",
    "LLMConfig",
    "VisionLLMConfig",
    "RuntimeConfig",
    "PlatformConfig",
    "CorpusConfig",
    "IntentConfig",
    "IntentJevConfig",
    "SecurityConfig",
    "ClassifierConfig",
    "RagConfig",
    "EmbeddingConfig",
    "RerankConfig",
    "RetrieverConfig",
    "QueryRewriteConfig",
    "ChunkerConfig",
    "MinioConfig",
    "StorageConfig",
    "RagToolsConfig",
    "MemoryConfig",
    "AgentsConfig",
]
