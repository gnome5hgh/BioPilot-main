"""配置 schema：把 dataclass 树描述成可渲染、可校验的字段清单。

这里是「设置页能看到什么、能改什么、怎么校验」的唯一来源：

- 字段全集从 ``sections.py`` 的 dataclass 树遍历得到，不在前端或接口里手抄；
- 引导层字段（数据库连接串、外部服务地址、本机路径）只读展示，不允许经页面写入；
- 密钥字段（``*.api_key``）单独标记，读取时只回显「是否已配置 + 末 4 位」；
- ``requires_restart`` 标记改完必须重启引擎才生效的字段（RAG 与平台客户端是
  进程级单例，捕获的是启动时的配置快照）。

路径统一用点号连接（``rag.embedding.api_key``），与 env 派生规则一一对应。
"""
from __future__ import annotations

import os
from dataclasses import fields, is_dataclass
from typing import Any

from biopilot.config.schemas.sections import CONTEXT_SIZE_TYPES, ContextSize

#: 配置作用域：目前只有全局一份；将来的用户级配置另表存、按 user_id 合并。
SCOPE_GLOBAL = "global"

#: 只读的引导层字段：进程启动前就要知道、或跟这台机器/这套部署绑定。
#: 它们由环境变量（或本地 .env）提供，设置页只展示，不接受写入。
BOOTSTRAP_PATHS: frozenset[str] = frozenset({
    "runtime.workspace",
    "runtime.user_cache_dir",
    "runtime.memory_dsn",
    "runtime.agents_dir",
    "platform.base_url",
    "platform.internal_token",
    "corpus.analysis_dir",
    "corpus.research_dir",
    "rag.storage.uri",
    "rag.storage.collection",
    "rag.storage.minio.endpoint",
    "rag.storage.minio.access_key",
    "rag.storage.minio.secret_key",
    "rag.storage.minio.bucket",
    "rag.storage.minio.secure",
    "compaction.tool_results.local_dir",
})

#: 必须重启引擎才生效的字段：RAGService 与平台 HTTP 客户端都是进程级单例，
#: 它们捕获的是创建时的配置；改这些值不会影响已经在跑的进程。
RESTART_PREFIXES: tuple[str, ...] = ("rag.",)
RESTART_PATHS: frozenset[str] = frozenset({
    "platform.search_timeout",
    "platform.transfer_timeout",
})

#: 用标签编辑器（逗号分隔）而不是 JSON 文本框的字符串列表。
TAG_PATHS: frozenset[str] = frozenset({
    "security.pre_approved_tools",
    "security.sandbox.read_roots",
})

#: 枚举字段及其可选值。前端渲染成下拉框。
ENUM_OPTIONS: dict[str, list[dict[str, str]]] = {
    "runtime.confirm_above": [
        {"value": "low", "label": "严格（中风险及以上都问）"},
        {"value": "medium", "label": "标准（高风险及以上才问）"},
        {"value": "high", "label": "宽松（仅严重风险询问）"},
        {"value": "critical", "label": "最宽松（几乎不询问）"},
    ],
    "compaction.keep.type": [
        {"value": "messages", "label": "按消息条数"},
        {"value": "tokens", "label": "按 token 数"},
        {"value": "fraction", "label": "按窗口比例"},
    ],
}

#: 分组顺序与说明。key 是顶层配置段，用于前端分栏。
GROUP_LAYOUT: list[dict[str, str]] = [
    {"key": "llm", "label": "对话模型", "description": "主模型的端点、模型名与调用参数；密钥只写不回显。"},
    {"key": "vision", "label": "视觉模型", "description": "图表与图片理解使用的多模态模型。"},
    {"key": "intent", "label": "意图识别", "description": "可选的预处理层，只注入信号，不参与派发决策。"},
    {"key": "security", "label": "安全", "description": "确认档位、预批准工具、语义判定与代码沙箱。"},
    {"key": "rag", "label": "检索增强", "description": "嵌入、精排、混合检索与分块参数；改动后需重启引擎。"},
    {"key": "memory", "label": "记忆", "description": "轮末后台整合的开关与节流窗口。"},
    {"key": "compaction", "label": "上下文压缩", "description": "窗口接近上限时的摘要压缩与外置策略。"},
    {"key": "agents", "label": "子代理", "description": "各角色的超时与 ReAct 轮数预算。"},
    {"key": "runtime", "label": "运行时", "description": "多模型清单、安全档位与网页终端开关。"},
    {"key": "platform", "label": "平台后端", "description": "Java 平台内部调用的超时参数。"},
    {"key": "session", "label": "终端会话", "description": "REPL 恢复时的历史回放行为。"},
    {"key": "bootstrap", "label": "部署引导", "description": "由环境变量提供、页面只读；换部署时在这里核对。"},
]

#: 每个分组内的分节顺序；字段按「最长前缀」归属分节。
SECTION_LAYOUT: dict[str, list[dict[str, str]]] = {
    "llm": [
        {"key": "llm", "label": "主模型", "description": "所有对话与工具调用共用；摘要模型留空时也用它。"},
    ],
    "vision": [
        {"key": "vision", "label": "视觉模型", "description": "独立的视觉端点，未配置时图表分析降级。"},
    ],
    "intent": [
        {"key": "intent", "label": "意图识别", "description": "关闭时整套意图层不装配。"},
        {"key": "intent.jev", "label": "判定服务", "description": "Vercel AI Gateway 决策模型；启用前需启动探测通过。"},
    ],
    "security": [
        {"key": "security", "label": "安全策略", "description": "外部来源工具默认逐次确认；预批准只降档、不旁路。"},
        {"key": "security.classifier", "label": "语义判定", "description": "可选层；端点或密钥缺失时整层不装配。"},
        {"key": "security.sandbox", "label": "代码沙箱", "description": "run_python 的容器政策；执行类工具必须在进程外隔离。"},
    ],
    "rag": [
        {"key": "rag", "label": "检索通用", "description": "跨子模块的开关。"},
        {"key": "rag.embedding", "label": "嵌入", "description": "稠密检索与索引的向量化端点。"},
        {"key": "rag.rerank", "label": "精排", "description": "留空端点/密钥时继承嵌入配置。"},
        {"key": "rag.retriever", "label": "混合检索", "description": "BM25 与向量的候选数、融合参数与最终条数。"},
        {"key": "rag.query_rewrite", "label": "查询改写", "description": "留空端点/密钥时继承主模型。"},
        {"key": "rag.chunker", "label": "分块", "description": "改动会触发配方哈希变化并全量重索引。"},
        {"key": "rag.storage", "label": "向量库调优", "description": "只放调优参数；地址与凭据在部署引导里。"},
        {"key": "rag.tools", "label": "检索工具", "description": "工具返回内容的展示参数。"},
    ],
    "memory": [
        {"key": "memory", "label": "记忆整合", "description": "轮末后台整合的开关与节流。"},
    ],
    "session": [
        {"key": "session", "label": "终端恢复", "description": "只影响 REPL；网页会话不受影响。"},
    ],
    "agents": [
        {"key": "agents", "label": "子代理预算", "description": "表内没有的角色使用类默认值。"},
    ],
    "compaction": [
        {"key": "compaction", "label": "压缩策略", "description": "触发条件任一满足即压缩。"},
        {"key": "compaction.keep", "label": "保留策略", "description": "压缩后保留多少近期上下文。"},
        {"key": "compaction.tool_results", "label": "工具结果外置", "description": "超过阈值的工具结果转存对象存储，窗口里只留指针。"},
    ],
    "runtime": [
        {"key": "runtime", "label": "运行时", "description": "会话级模型选择、安全档位与终端开关。"},
    ],
    "platform": [
        {"key": "platform", "label": "内部调用", "description": "文件传输与检索请求的超时。"},
    ],
    "bootstrap": [
        {"key": "runtime", "label": "运行时路径", "description": "运行数据根、记忆库与 Agent 插件目录。"},
        {"key": "platform", "label": "平台连接", "description": "Java 平台地址与内部 token。"},
        {"key": "corpus", "label": "产物目录", "description": "分析产物与研究产物的落点；笔记与论文走平台存储。"},
        {"key": "rag.storage", "label": "向量库与对象存储", "description": "Milvus 地址、集合名与 MinIO 连接凭据。"},
        {"key": "compaction.tool_results", "label": "外置回退", "description": "对象存储不可用时的本地回退目录。"},
    ],
}

#: 字段中文名与补充说明。未列出的字段用路径末段兜底。
FIELD_META: dict[str, dict[str, str]] = {
    # ── llm / vision ──
    "llm.base_url": {"label": "接口地址", "help": "OpenAI 兼容端点，换服务商只改这里。"},
    "llm.api_key": {"label": "密钥", "help": "留空 = 未配置；写入后只显示末 4 位。"},
    "llm.model": {"label": "模型名"},
    "llm.max_tokens": {"label": "单次输出上限", "help": "过小会把长笔记或大参数文件静默截断。"},
    "llm.temperature": {"label": "采样温度"},
    "llm.timeout_connect": {"label": "连接超时（秒）"},
    "llm.timeout_read": {"label": "读取超时（秒）"},
    "llm.max_retries": {"label": "重试次数"},
    "llm.context_window": {"label": "上下文窗口（token）", "help": "换模型必须同步改，填大了会撞上限。"},
    "vision.base_url": {"label": "接口地址"},
    "vision.api_key": {"label": "密钥"},
    "vision.model": {"label": "模型名"},
    "vision.max_tokens": {"label": "单次输出上限"},
    "vision.timeout_connect": {"label": "连接超时（秒）"},
    "vision.timeout_read": {"label": "读取超时（秒）"},
    "vision.max_retries": {"label": "重试次数"},
    "vision.temperature": {"label": "采样温度"},
    "vision.context_window": {"label": "上下文窗口（token）"},
    # ── runtime / platform ──
    "runtime.workspace": {"label": "运行数据根"},
    "runtime.user_cache_dir": {"label": "用户缓存根", "help": "按用户隔离的派生缓存（附件副本、技能物化）；留空按安装根派生。"},
    "runtime.memory_dsn": {"label": "记忆库连接串"},
    "runtime.agents_dir": {"label": "Agent 插件目录"},
    "runtime.models": {"label": "多模型清单", "help": "JSON 数组，每项 {name, model, base_url, api_key}；api_key 只显示末 4 位。"},
    "runtime.confirm_above": {"label": "安全确认档位", "help": "风险高于该档的工具执行前会弹确认。"},
    "runtime.allow_host_shell": {"label": "允许网页终端", "help": "宿主 shell 拥有服务账号权限；共享部署保持关闭。"},
    "platform.base_url": {"label": "Java 平台地址"},
    "platform.internal_token": {"label": "内部调用 Token"},
    "platform.search_timeout": {"label": "检索超时（秒）"},
    "platform.transfer_timeout": {"label": "文件传输超时（秒）"},
    # ── corpus ──
    "corpus.analysis_dir": {"label": "分析产物目录"},
    "corpus.research_dir": {"label": "研究产物目录"},
    # ── intent ──
    "intent.enabled": {"label": "启用意图识别"},
    "intent.history_messages": {"label": "参考对话条数"},
    "intent.jev.base_url": {"label": "判定服务地址"},
    "intent.jev.api_key": {"label": "判定服务密钥"},
    "intent.jev.model": {"label": "判定模型"},
    "intent.jev.timeout": {"label": "判定超时（秒）"},
    "intent.jev.max_retries": {"label": "判定重试次数"},
    "intent.jev.zero_data_retention": {"label": "要求零数据保留", "help": "本层会发送用户对话史，默认开启。"},
    "intent.jev.only_provider": {"label": "固定提供方", "help": "留空由网关路由。"},
    # ── security ──
    "security.pre_approved_tools": {"label": "预批准工具", "help": "逗号分隔；只降档到免问上限内，不旁路确认。"},
    "security.classifier.enabled": {"label": "启用语义判定"},
    "security.classifier.base_url": {"label": "判定网关地址"},
    "security.classifier.api_key": {"label": "判定网关密钥"},
    "security.classifier.model": {"label": "判定模型"},
    "security.classifier.timeout": {"label": "判定超时（秒）"},
    "security.classifier.max_retries": {"label": "判定重试次数"},
    "security.sandbox.enabled": {"label": "启用代码沙箱"},
    "security.sandbox.image": {"label": "沙箱镜像"},
    "security.sandbox.network": {"label": "允许容器联网", "help": "默认断网；分析依赖应预装进镜像。"},
    "security.sandbox.read_roots": {"label": "只读挂载根", "help": "逗号分隔的语义根名，挂到容器 /corpus/<根名>。"},
    "security.sandbox.memory": {"label": "内存上限"},
    "security.sandbox.cpus": {"label": "CPU 上限"},
    "security.sandbox.pids_limit": {"label": "进程数上限"},
    "security.sandbox.timeout_s": {"label": "执行超时（秒）"},
    # ── rag ──
    "rag.store_images": {"label": "保存图表原图", "help": "关闭后退回纯文本，不再渲染与写对象。"},
    "rag.embedding.base_url": {"label": "接口地址"},
    "rag.embedding.api_key": {"label": "密钥"},
    "rag.embedding.embed_model": {"label": "嵌入模型"},
    "rag.embedding.batch_size": {"label": "批大小"},
    "rag.embedding.timeout": {"label": "超时（秒）"},
    "rag.embedding.max_retries": {"label": "重试次数"},
    "rag.rerank.base_url": {"label": "接口地址", "help": "留空继承嵌入端点。"},
    "rag.rerank.api_key": {"label": "密钥", "help": "留空继承嵌入密钥。"},
    "rag.rerank.model": {"label": "精排模型"},
    "rag.rerank.timeout": {"label": "超时（秒）"},
    "rag.rerank.max_retries": {"label": "重试次数"},
    "rag.retriever.top_k": {"label": "最终返回条数"},
    "rag.retriever.bm25_topk": {"label": "BM25 候选数"},
    "rag.retriever.vector_topk": {"label": "向量候选数"},
    "rag.retriever.rerank_candidates": {"label": "精排候选数"},
    "rag.retriever.rrf_k": {"label": "RRF 常数"},
    "rag.query_rewrite.base_url": {"label": "接口地址", "help": "留空继承主模型。"},
    "rag.query_rewrite.api_key": {"label": "密钥", "help": "留空继承主模型密钥。"},
    "rag.query_rewrite.model": {"label": "改写模型", "help": "留空继承主模型。"},
    "rag.query_rewrite.history_messages": {"label": "参考对话条数"},
    "rag.query_rewrite.rewrite_num": {"label": "改写份数"},
    "rag.query_rewrite.max_queries": {"label": "最大查询数"},
    "rag.query_rewrite.max_query_chars": {"label": "单查询字符上限"},
    "rag.chunker.max_tokens": {"label": "分块 token 上限"},
    "rag.chunker.overlap_tokens": {"label": "分块重叠 token"},
    "rag.storage.uri": {"label": "Milvus 地址"},
    "rag.storage.collection": {"label": "向量集合名"},
    "rag.storage.batch_size": {"label": "写入批大小"},
    "rag.storage.timeout": {"label": "读超时（秒）"},
    "rag.storage.write_timeout": {"label": "写超时（秒）"},
    "rag.storage.minio.endpoint": {"label": "MinIO 地址"},
    "rag.storage.minio.access_key": {"label": "MinIO Access Key"},
    "rag.storage.minio.secret_key": {"label": "MinIO Secret Key"},
    "rag.storage.minio.bucket": {"label": "对象存储桶"},
    "rag.storage.minio.secure": {"label": "MinIO TLS"},
    "rag.tools.excerpt_chars": {"label": "摘要字符数"},
    # ── memory / session / agents ──
    "memory.consolidation_enabled": {"label": "启用记忆整合"},
    "memory.debounce_seconds": {"label": "静默窗口（秒）"},
    "memory.max_delay_seconds": {"label": "最大延迟（秒）"},
    "session.resume_replay": {"label": "终端回放历史"},
    "session.resume_replay_limit": {"label": "回放条数上限", "help": "0 = 回放整个窗口。"},
    "agents.timeouts": {"label": "子代理超时", "help": "JSON 对象：角色名 → 秒数；表外角色用类默认值。"},
    "agents.max_turns": {"label": "子代理轮数", "help": "JSON 对象：角色名 → ReAct 轮数上限。"},
    # ── compaction ──
    "compaction.enabled": {"label": "启用上下文压缩"},
    "compaction.trigger": {"label": "触发条件", "help": "JSON 数组，任一满足即触发；type 取 tokens/messages/fraction。"},
    "compaction.keep.type": {"label": "保留计量方式"},
    "compaction.keep.value": {"label": "保留数量"},
    "compaction.trim_tokens_to_summarize": {"label": "摘要输入上限（token）"},
    "compaction.summary_max_words": {"label": "摘要长度上限（token）"},
    "compaction.summary_model_name": {"label": "摘要专用模型", "help": "留空使用主模型。"},
    "compaction.context_size": {"label": "显式有效窗口", "help": "0 = 由模型窗口推导；一般保持 0。"},
    "compaction.tool_results.persist_threshold_chars": {"label": "外置阈值（字符）"},
    "compaction.tool_results.preview_chars": {"label": "预览字符数"},
    "compaction.tool_results.local_dir": {"label": "本地回退目录"},
}

#: 枚举字段（含 JSON 字段内部的枚举约束，校验时单独处理）。
#: 与 core 的 RiskOrder 对齐；config 不依赖 core，保持这层的独立声明。
CONFIRM_LEVELS = ("low", "medium", "high", "critical")

#: 数值字段的上下界。未列出的整数按「>= 0」校验，浮点按「>= 0」校验。
#: 元组含义：(最小值, 最大值, 是否开区间下界)。
_NUMERIC_RULES: dict[str, tuple[float | None, float | None, bool]] = {
    "llm.max_tokens": (1, None, False),
    "llm.context_window": (1, None, False),
    "llm.timeout_connect": (0, None, True),
    "llm.timeout_read": (0, None, True),
    "llm.temperature": (0, None, False),
    "vision.max_tokens": (1, None, False),
    "vision.context_window": (1, None, False),
    "vision.timeout_connect": (0, None, True),
    "vision.timeout_read": (0, None, True),
    "platform.search_timeout": (0, None, True),
    "platform.transfer_timeout": (0, None, True),
    "intent.history_messages": (0, None, False),
    "intent.jev.timeout": (0, None, True),
    "security.classifier.timeout": (0, None, True),
    "security.sandbox.cpus": (0, None, True),
    "security.sandbox.pids_limit": (1, None, False),
    "security.sandbox.timeout_s": (1, None, False),
    "rag.embedding.batch_size": (1, None, False),
    "rag.embedding.timeout": (0, None, True),
    "rag.rerank.timeout": (0, None, True),
    "rag.retriever.top_k": (0, None, False),
    "rag.retriever.bm25_topk": (0, None, False),
    "rag.retriever.vector_topk": (0, None, False),
    "rag.retriever.rerank_candidates": (0, None, False),
    "rag.retriever.rrf_k": (1, None, False),
    "rag.query_rewrite.history_messages": (0, None, False),
    "rag.query_rewrite.rewrite_num": (1, None, False),
    "rag.query_rewrite.max_queries": (1, None, False),
    "rag.query_rewrite.max_query_chars": (1, None, False),
    "rag.chunker.max_tokens": (1, None, False),
    "rag.chunker.overlap_tokens": (0, None, False),
    "rag.storage.batch_size": (1, None, False),
    "rag.storage.timeout": (0, None, True),
    "rag.storage.write_timeout": (0, None, True),
    "rag.tools.excerpt_chars": (0, None, False),
    "memory.debounce_seconds": (0, None, False),
    "memory.max_delay_seconds": (0, None, False),
    "session.resume_replay_limit": (0, None, False),
    "compaction.keep.value": (0, None, False),
    "compaction.trim_tokens_to_summarize": (0, None, False),
    "compaction.summary_max_words": (1, None, False),
    "compaction.context_size": (0, None, False),
    "compaction.tool_results.persist_threshold_chars": (1, None, False),
    "compaction.tool_results.preview_chars": (0, None, False),
}

#: 必须非空的字符串字段。
_NON_EMPTY_STRINGS: frozenset[str] = frozenset({
    "llm.model",
    "vision.model",
    "rag.embedding.embed_model",
    "rag.rerank.model",
    "security.sandbox.image",
})


class ConfigValidationError(ValueError):
    """配置校验失败：带字段路径，方便前端定位到具体输入框。"""

    def __init__(self, path: str, message: str):
        """记录失败字段与原因。

        Args:
            path: 配置字段路径（点号连接）。
            message: 面向用户的失败原因。
        """
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def env_name(path: str) -> str:
    """把配置路径换成派生环境变量名。

    Args:
        path: 配置字段路径（如 ``rag.storage.uri``）。

    Returns:
        环境变量名（如 ``BIOPILOT_RAG_STORAGE_URI``）。
    """
    return "BIOPILOT_" + path.replace(".", "_").upper()


def iter_leaves(node, prefix: tuple[str, ...] = ()):
    """深度遍历 dataclass，产出（路径, 标量/集合值）二元组。

    嵌套 dataclass 继续下行；list/dict 作为整体叶子返回（与加载器的覆写语义一致）。

    Args:
        node: 任意 dataclass 实例。
        prefix: 当前路径前缀。

    Yields:
        tuple[str, Any]: 点号路径与实际值。
    """
    for f in fields(node):
        cur = getattr(node, f.name)
        path = prefix + (f.name,)
        if is_dataclass(cur) and not isinstance(cur, type):
            yield from iter_leaves(cur, path)
        else:
            yield ".".join(path), cur


def default_map() -> dict[str, Any]:
    """返回全部字段的默认值映射（路径 → 值）。"""
    # 延迟导入：loader 依赖本模块做 DB 覆盖，模块级互相导入会成环。
    from biopilot.config.services.loader import BioPilotConfig

    return dict(iter_leaves(BioPilotConfig()))


def effective_map(config) -> dict[str, Any]:
    """返回加载后配置的全部字段值映射（路径 → 值，含引导层）。"""
    return dict(iter_leaves(config))


#: 除 ``*.api_key`` 之外、同样按密钥处理的字段。
EXTRA_SECRET_PATHS: frozenset[str] = frozenset({
    "platform.internal_token",
    "rag.storage.minio.secret_key",
    # 列表里嵌套密钥：整份加密，读取时对每项 api_key 做掩码。
    "runtime.models",
})


def is_secret(path: str) -> bool:
    """判断字段是否按密钥处理（只回显末 4 位、单独加密存储）。"""
    return path.endswith(".api_key") or path in EXTRA_SECRET_PATHS


def mask_dsn(dsn: Any) -> str:
    """隐去连接串里的口令，避免设置页把数据库密码显示出来。

    Args:
        dsn: 连接串，形如 ``mysql://user:pass@host:port/db``。

    Returns:
        口令替换为 ``***`` 的连接串；解析不了时原样返回（仍只读展示）。
    """
    text = "" if dsn is None else str(dsn)
    if "@" not in text or "://" not in text:
        return text
    scheme, rest = text.split("://", 1)
    credentials, host = rest.rsplit("@", 1)
    if ":" not in credentials:
        return text
    user, _ = credentials.split(":", 1)
    return f"{scheme}://{user}:***@{host}"


def is_editable(path: str) -> bool:
    """判断字段是否允许经设置页写入（引导层只读）。"""
    return path not in BOOTSTRAP_PATHS


def requires_restart(path: str) -> bool:
    """判断字段改动后是否需要重启引擎（进程级单例捕获了旧配置）。"""
    return path in RESTART_PATHS or path.startswith(RESTART_PREFIXES)


def is_env_set(path: str) -> bool:
    """判断该字段是否被环境变量（含 .env）显式设置。

    ``platform.internal_token`` 的规范来源是共享的 ``BIOPILOT_INTERNAL_TOKEN``，
    它同时服务入站校验，因此单独识别。

    Args:
        path: 配置字段路径。

    Returns:
        bool: 环境里有非空值时为 True。
    """
    if os.environ.get(env_name(path)):
        return True
    # 部署约定用 BIOPILOT_MEMORY_MYSQL_DSN 指代 runtime.memory_dsn（与 MemoryDB 共用）。
    if path == "runtime.memory_dsn" and os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN"):
        return True
    if path == "platform.internal_token" and os.environ.get("BIOPILOT_INTERNAL_TOKEN"):
        return True
    return False


def jsonable(value: Any) -> Any:
    """把配置值转成可 JSON 序列化的结构（dataclass → dict）。"""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    return value


def mask_secret(value: Any) -> dict[str, Any]:
    """把密钥值替换成「是否已配置 + 末 4 位」的信封。

    Args:
        value: 明文密钥（可能为空）。

    Returns:
        dict: ``{"set": bool, "last4": str}``。
    """
    text = "" if value is None else str(value)
    return {"set": bool(text), "last4": text[-4:] if text else ""}


def mask_model_entries(entries: Any) -> list[dict[str, Any]]:
    """把多模型清单里的 api_key 换成掩码信封，其余字段原样返回。

    Args:
        entries: ``runtime.models`` 的列表值。

    Returns:
        list[dict]: 每项保留 name/model/base_url，密钥换成 ``api_key_set`` /
        ``api_key_last4``。
    """
    masked: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        key = item.pop("api_key", "")
        item["api_key_set"] = bool(key)
        item["api_key_last4"] = str(key)[-4:] if key else ""
        masked.append(item)
    return masked


def flatten_leaves(data: Any, defaults: dict[str, Any] | None = None,
                   prefix: tuple[str, ...] = ()):
    """把嵌套配置展开成（点号路径, 值），保留 schema 里的 dict/list 叶子。

    ``agents.timeouts`` / ``runtime.models`` 这类字段在默认值里是整体叶子；
    走普通递归会把它们拆成内部的键（``agents.timeouts.note-agent``），既不是
    合法配置路径，也会让导入/来源判断失效。传入 ``defaults`` 后，命中叶子路径
    即整体产出、不再向下。

    Args:
        data: 嵌套配置（YAML 或数据库 content）。
        defaults: 默认值映射（路径 → 值）；None 表示纯结构展开。
        prefix: 当前路径前缀。

    Yields:
        tuple[str, Any]: 点号路径与对应值。
    """
    if isinstance(data, dict):
        for key, value in data.items():
            path = ".".join(prefix + (str(key),))
            if defaults is not None and path in defaults:
                yield path, value
                continue
            if isinstance(value, dict):
                yield from flatten_leaves(value, defaults, prefix + (str(key),))
            else:
                yield path, value
        return
    yield ".".join(prefix), data


def nest_patches(patches: dict[str, Any]) -> dict[str, Any]:
    """把扁平路径映射还原成嵌套字典，供加载器的递归合并使用。

    Args:
        patches: 路径 → 值的扁平映射。

    Returns:
        dict: 与配置树同构的嵌套覆盖。
    """
    root: dict[str, Any] = {}
    for path, value in patches.items():
        node = root
        segments = path.split(".")
        for seg in segments[:-1]:
            node = node.setdefault(seg, {})
        node[segments[-1]] = value
    return root


def _coerce_scalar(path: str, value: Any, default: Any) -> Any:
    """按默认值的类型转换并校验单个标量。

    Args:
        path: 字段路径。
        value: 前端提交的值。
        default: 默认值（提供目标类型）。

    Returns:
        转换后的值。

    Raises:
        ConfigValidationError: 类型不匹配或数值越界。
    """
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ConfigValidationError(path, "需要布尔值")
    if isinstance(value, bool):
        raise ConfigValidationError(path, "需要数字，收到布尔值")
    if isinstance(default, int):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ConfigValidationError(path, "需要整数") from None
        return _check_range(path, number)
    if isinstance(default, float):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ConfigValidationError(path, "需要数字") from None
        return _check_range(path, number)
    if default is None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigValidationError(path, "需要字符串或空值")
        return value
    if isinstance(default, str):
        if not isinstance(value, str):
            raise ConfigValidationError(path, "需要字符串")
        if path in _NON_EMPTY_STRINGS and not value.strip():
            raise ConfigValidationError(path, "不能为空")
        return value
    raise ConfigValidationError(path, "不支持的字段类型")


def _check_range(path: str, number: float) -> float:
    """按 ``_NUMERIC_RULES`` 校验数值范围。

    Args:
        path: 字段路径。
        number: 已转换的数值。

    Returns:
        原数值。

    Raises:
        ConfigValidationError: 越界。
    """
    rule = _NUMERIC_RULES.get(path)
    if rule is None:
        if number < 0:
            raise ConfigValidationError(path, "不能为负数")
        return number
    minimum, maximum, exclusive = rule
    if minimum is not None:
        if exclusive and number <= minimum:
            raise ConfigValidationError(path, f"必须大于 {minimum:g}")
        if not exclusive and number < minimum:
            raise ConfigValidationError(path, f"不能小于 {minimum:g}")
    if maximum is not None and number > maximum:
        raise ConfigValidationError(path, f"不能大于 {maximum:g}")
    return number


def _validate_context_size(path: str, item: Any) -> dict[str, Any]:
    """校验单个 ContextSize 结构（压缩触发/保留）。"""
    if isinstance(item, ContextSize):
        item = {"type": item.type, "value": item.value}
    if not isinstance(item, dict):
        raise ConfigValidationError(path, "需要 {type, value} 对象")
    kind = item.get("type")
    if kind not in CONTEXT_SIZE_TYPES:
        raise ConfigValidationError(path, "type 只能是 tokens/messages/fraction")
    value = item.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigValidationError(path, "value 需要数字")
    if value < 0:
        raise ConfigValidationError(path, "value 不能为负数")
    if kind == "fraction" and value > 1:
        raise ConfigValidationError(path, "fraction 的 value 必须在 0~1 之间")
    return {"type": kind, "value": value}


def _validate_positive_int_map(path: str, value: Any) -> dict[str, int]:
    """校验「角色 → 正整数」映射（子代理超时/轮数）。"""
    if not isinstance(value, dict):
        raise ConfigValidationError(path, "需要 JSON 对象")
    result: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigValidationError(path, "键必须是非空字符串")
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise ConfigValidationError(path, f"{key} 的取值必须是正整数")
        result[key] = item
    return result


def _validate_models(path: str, value: Any) -> list[dict[str, Any]]:
    """校验多模型清单：每项至少要有 name 或 model。"""
    if not isinstance(value, list):
        raise ConfigValidationError(path, "需要 JSON 数组")
    result: list[dict[str, Any]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise ConfigValidationError(path, f"第 {index + 1} 项需要对象")
        item = dict(entry)
        if not str(item.get("name") or item.get("model") or "").strip():
            raise ConfigValidationError(path, f"第 {index + 1} 项缺少 name 或 model")
        for key in ("name", "model", "base_url", "api_key"):
            if key in item and item[key] is not None and not isinstance(item[key], str):
                raise ConfigValidationError(path, f"第 {index + 1} 项的 {key} 需要字符串")
        result.append(item)
    return result


def validate_value(path: str, value: Any, default: Any) -> Any:
    """校验并规范化一个待写入的配置值。

    Args:
        path: 字段路径。
        value: 前端提交的值。
        default: 该字段的默认值（提供类型与结构）。

    Returns:
        规范化后的值（可直接写库、也可由加载器合并）。

    Raises:
        ConfigValidationError: 路径不可写、类型不符或越界。
    """
    if path in BOOTSTRAP_PATHS:
        raise ConfigValidationError(path, "引导层字段由环境变量提供，页面不可写")
    if path in TAG_PATHS:
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ConfigValidationError(path, "需要字符串数组")
        return [v.strip() for v in value if v.strip()]
    if path == "runtime.models":
        return _validate_models(path, value)
    if path in ("agents.timeouts", "agents.max_turns"):
        return _validate_positive_int_map(path, value)
    if path == "compaction.trigger":
        if not isinstance(value, list) or not value:
            raise ConfigValidationError(path, "至少需要一个触发条件")
        return [_validate_context_size(path, item) for item in value]
    if path == "runtime.confirm_above":
        if value not in CONFIRM_LEVELS:
            raise ConfigValidationError(path, "只能是 low/medium/high/critical")
        return value
    if path == "compaction.keep.type":
        if value not in CONTEXT_SIZE_TYPES:
            raise ConfigValidationError(path, "只能是 tokens/messages/fraction")
        return value
    if path == "compaction.summary_model_name":
        if value is not None and not isinstance(value, str):
            raise ConfigValidationError(path, "需要字符串或空值")
        return value or None
    if isinstance(default, (list, dict)):
        raise ConfigValidationError(path, "该字段需要结构化 JSON 值")
    return _coerce_scalar(path, value, default)


def validate_patches(patches: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """批量校验补丁，返回规范化后的补丁。

    Args:
        patches: 路径 → 值的扁平映射。
        defaults: 默认值映射；缺省时现取。

    Returns:
        规范化后的补丁（键顺序保持提交顺序）。

    Raises:
        ConfigValidationError: 任一路径或取值非法。
    """
    defaults = defaults or default_map()
    normalized: dict[str, Any] = {}
    for path, value in patches.items():
        if path not in defaults:
            raise ConfigValidationError(path, "未知的配置项")
        normalized[path] = validate_value(path, value, defaults[path])
    return normalized


def build_schema() -> list[dict[str, Any]]:
    """构造分组后的字段清单（不含当前值，由设置接口另行合并）。

    Returns:
        list[dict]: 按 ``GROUP_LAYOUT`` 排序的分组，每组含 ``sections``，
        每节含 ``fields``；字段带 path/label/type/widget/secret/editable/
        requires_restart/default/options/help。
    """
    defaults = default_map()
    # 每个字段归属到「最长匹配前缀」的分节；引导层单独成组。
    section_keys: list[tuple[str, str, dict[str, str]]] = []
    for group_key, sections in SECTION_LAYOUT.items():
        for section in sections:
            section_keys.append((group_key, section["key"], section))

    groups: list[dict[str, Any]] = []
    for group in GROUP_LAYOUT:
        is_bootstrap_group = group["key"] == "bootstrap"
        # 引导层字段只在「部署引导」组展示；普通分组里剔除它们，避免重复渲染。
        candidate_paths = [
            path for path in defaults
            if (path in BOOTSTRAP_PATHS) == is_bootstrap_group
        ]
        sections_out: list[dict[str, Any]] = []
        for section in SECTION_LAYOUT.get(group["key"], []):
            fields_out = [
                _field_descriptor(path, defaults[path])
                for path in candidate_paths
                if _belongs(path, section["key"], section_keys)
            ]
            if fields_out:
                sections_out.append({
                    "key": section["key"],
                    "label": section["label"],
                    "description": section.get("description", ""),
                    "fields": fields_out,
                })
        if sections_out:
            groups.append({**group, "sections": sections_out})
    return groups


def _belongs(path: str, section_key: str, all_sections: list[tuple[str, str, dict]]) -> bool:
    """判断字段是否属于该分节（最长前缀匹配）。

    Args:
        path: 字段路径。
        section_key: 候选分节前缀。
        all_sections: 全部分节（用于确认没有更长前缀）。

    Returns:
        bool: 该字段的最长匹配前缀正好是 ``section_key``。
    """
    if not (path == section_key or path.startswith(section_key + ".")):
        return False
    longest = section_key
    for _, candidate, _ in all_sections:
        if path == candidate or path.startswith(candidate + "."):
            if len(candidate) > len(longest):
                longest = candidate
    return longest == section_key


def _field_descriptor(path: str, default: Any) -> dict[str, Any]:
    """构造单个字段的描述对象。"""
    meta = FIELD_META.get(path, {})
    widget = _widget(path, default)
    descriptor: dict[str, Any] = {
        "path": path,
        "label": meta.get("label") or path.split(".")[-1].replace("_", " "),
        "help": meta.get("help", ""),
        "type": _type_name(default),
        "widget": widget,
        "default": jsonable(default),
        "secret": is_secret(path),
        "editable": is_editable(path),
        "requires_restart": requires_restart(path),
    }
    if path in ENUM_OPTIONS:
        descriptor["options"] = ENUM_OPTIONS[path]
    return descriptor


def _type_name(default: Any) -> str:
    """把默认值映射成前端使用的类型名。"""
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "float"
    if isinstance(default, str):
        return "string"
    if isinstance(default, list):
        return "list"
    if isinstance(default, dict):
        return "dict"
    if default is None:
        return "string"
    return "json"


def _widget(path: str, default: Any) -> str:
    """决定前端用哪种输入控件。"""
    # 多模型清单虽是密钥载体（整份加密、条目里的 api_key 掩码），编辑控件仍是
    # JSON 编辑器：它是数组，不是单个口令。前端按 widget 而不是 secret 选控件。
    if path == "runtime.models":
        return "json"
    if is_secret(path):
        return "password"
    if path in ENUM_OPTIONS:
        return "select"
    if isinstance(default, bool):
        return "switch"
    if isinstance(default, (int, float)):
        return "number"
    if isinstance(default, list):
        return "tags" if path in TAG_PATHS else "json"
    if isinstance(default, dict):
        return "json"
    return "text"


__all__ = [
    "BOOTSTRAP_PATHS",
    "ConfigValidationError",
    "ENUM_OPTIONS",
    "GROUP_LAYOUT",
    "SCOPE_GLOBAL",
    "build_schema",
    "default_map",
    "effective_map",
    "env_name",
    "flatten_leaves",
    "is_editable",
    "is_env_set",
    "is_secret",
    "jsonable",
    "mask_model_entries",
    "mask_dsn",
    "mask_secret",
    "nest_patches",
    "requires_restart",
    "validate_patches",
    "validate_value",
]
