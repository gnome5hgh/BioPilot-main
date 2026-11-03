"""配置加载与派生：三级优先级 + 递归合并 + env 按路径派生。

优先级从低到高：dataclass 默认值（``sections.py``）→ ``config.yaml``（可选、纯覆盖）
→ 环境变量（``BIOPILOT_`` + 配置路径大写，``_`` 连接）。嵌套 dataclass 逐层递归；
dict/list 自由字段仅 YAML 可配；标量字段两者都可覆写。
"""
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

#: 仓库安装根（本文件位于 biopilot/config/services/，向上三级即仓库根）。
#: 相对路径的缓存目录按它解析，避免随启动 cwd 漂移。
_INSTALL_ROOT = Path(__file__).resolve().parents[3]

from biopilot.config.schemas.sections import (
    AgentsConfig,
    CompactionSettings,
    CorpusConfig,
    IntentConfig,
    LLMConfig,
    MemoryConfig,
    PlatformConfig,
    RagConfig,
    RuntimeConfig,
    ClassifierConfig,
    SecurityConfig,
    SessionConfig,
    VisionLLMConfig,
)


# ── 通用合并原语 ────────────────────────────────────────────────────────────

def _is_scalar(val) -> bool:
    """标量判定：str/int/float/bool/None——只有这些才允许 YAML/env 覆写。

    非 dataclass、非 dict/list 的自定义对象没有通用覆写语义：把 YAML/env 值直接
    setattr 成裸 dict/str 会静默破坏其行为，必须跳过。

    Args:
        val: 任意字段当前值

    Returns:
        True 表示是可被 YAML/env 覆写的标量（str/int/float/bool/None）。
    """
    return val is None or isinstance(val, (str, int, float, bool))


def _coerce(current, val):
    """把标量 val 转成与 current 同类的类型（env 恒字符串 / YAML 可能写错类型）。

    - bool：字符串按 "1"/"true"/"yes" 判真（"false" 必须落 False）；
    - int / float：直接转换；
    - str：原样保留；
    - 其余（dict/list 等）：原样。

    Args:
        current: 字段当前值（提供目标类型）
        val: YAML/env 来的新值（env 恒为字符串）

    Returns:
        转换到与 current 同类型的值（dict/list 等原样返回）。
    """
    if isinstance(current, bool):
        return val.lower() in ("1", "true", "yes") if isinstance(val, str) else bool(val)
    if isinstance(current, int):
        return int(val)
    if isinstance(current, float):
        return float(val)
    return val


def _merge(node, raw) -> None:
    """通用递归合并：沿 ``dataclasses.fields()`` 下行，raw 覆盖 node。

    - 字段当前值是 dataclass → 递归（要求 raw 为 dict，否则跳过）；
    - 自由 dict/list 字段 → 整体赋值；
    - 标量 → 按目标字段当前类型转换（``_coerce``）；
    - 其余自定义对象 → 跳过（见 ``_is_scalar``）；
    - raw 里的未知键被忽略（沿用现有 hasattr 守卫精神，运行期不因陌生键崩）。

    Args:
        node: 任意 dataclass 实例（被就地覆写）
        raw: dict，YAML 覆盖值（非 dict 直接返回）
    """
    if not isinstance(raw, dict):
        return
    for f in fields(node):
        if f.name not in raw:
            continue
        cur = getattr(node, f.name)
        val = raw[f.name]
        if is_dataclass(cur) and not isinstance(cur, type):
            _merge(cur, val)
        elif isinstance(cur, (dict, list)):
            setattr(node, f.name, val)
        elif _is_scalar(cur):
            setattr(node, f.name, _coerce(cur, val))
        # else：非 dataclass 非集合非标量的自定义对象跳过覆写，
        #       不得把 YAML 值 setattr 成裸 dict/str。


@dataclass
class BioPilotConfig:
    """项目全局配置,聚合所有子系统的配置项。

    ``runtime.workspace`` 是运行时数据根目录,各子系统的数据写入统一走此路径。

    Attributes:
        llm: LLMConfig，LLM 连接
        vision: VisionLLMConfig，视觉模型连接
        runtime: RuntimeConfig，运行时基础设施
        platform: PlatformConfig，Java 平台后端连接（agent 调平台内部能力）
        corpus: CorpusConfig，语料库与产物路径
        intent: IntentConfig，意图识别
        security: SecurityConfig，安全模块（预批准名单）
        rag: RagConfig，RAG 检索栈
        memory: MemoryConfig，记忆系统
        session: SessionConfig，会话恢复
        agents: AgentsConfig，子 agent 配置
        compaction: CompactionSettings，上下文压缩
    """

    #: LLM 连接配置
    llm: LLMConfig = field(default_factory=LLMConfig)

    #: 视觉模型连接配置（多模态图表分析，独立于文本 LLM）
    vision: VisionLLMConfig = field(default_factory=VisionLLMConfig)

    #: 运行时基础设施（workspace / agents_dir / confirm_above）
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    #: Java 平台后端连接（内部检索、文档保存等外部能力）
    platform: PlatformConfig = field(default_factory=PlatformConfig)

    #: 语料库与产物路径
    corpus: CorpusConfig = field(default_factory=CorpusConfig)

    #: 意图识别子系统（总开关 + 编码器 + 路由器）
    intent: IntentConfig = field(default_factory=IntentConfig)

    #: 安全模块（外部来源工具的预批准名单 + 可选语义判定层）
    security: SecurityConfig = field(default_factory=SecurityConfig)

    #: RAG 检索栈（嵌入/检索/改写/切块/索引/存储/解析/工具）
    rag: RagConfig = field(default_factory=RagConfig)

    #: 记忆系统（consolidation 后台整合）
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    #: 会话恢复（屏上历史回放）
    session: SessionConfig = field(default_factory=SessionConfig)

    #: 子 agent 配置（timeouts 为 YAML-only 自由 dict）
    agents: AgentsConfig = field(default_factory=AgentsConfig)

    #: 上下文压缩配置（触发/保留/摘要参数；YAML 与 env 均可覆写）
    compaction: CompactionSettings = field(default_factory=CompactionSettings)

    @classmethod
    def from_env(cls, config_path: str | None = None) -> "BioPilotConfig":
        """工厂方法：依次加载 .env 兜底、可选 YAML、环境变量覆盖。

        返回值保证所有字段有值（至少为 dataclass 默认值）。

        Args:
            config_path: str | None，config.yaml 路径；None 用默认 "config.yaml"（不存在则跳过）

        Returns:
            加载完成的配置（.env → YAML → env 覆盖，并解析留空继承与绝对化 workspace）。
        """
        # 加载 .env 文件（不覆盖已有环境变量，即 OS 环境优先于 .env）
        load_dotenv()

        config = cls()
        config._load_yaml(config_path)  # 第一步：YAML 文件（优先级最低）
        config._load_env()               # 第二步：环境变量（覆盖 YAML 值）
        # trigger/keep 在 YAML 里是裸 dict，_merge 只做整体赋值、不实例化列表元素；
        # 加载完成后归一化成 ContextSize，后续判定才能直接读 .type/.value。
        config.compaction.normalize()
        # 留空继承：rag.query_rewrite ← llm、rag.rerank ← rag.embedding。
        # 必须在 YAML/env 全部加载后做——否则 env 覆盖会被继承值抢先顶掉。
        emb = config.rag.embedding
        # rag.rerank 留空逐项继承 rag.embedding（端点/key），与上面同一阶段。
        rr = config.rag.rerank
        rr.base_url = rr.base_url or emb.base_url
        rr.api_key = rr.api_key or emb.api_key
        qr = config.rag.query_rewrite
        qr.base_url = qr.base_url or config.llm.base_url
        qr.api_key = qr.api_key or config.llm.api_key
        # workspace 绝对化:相对 workspace(默认 ".biopilot")派生的根会被工作区校验二次拼接
        # 成 .biopilot/.biopilot/... 双前缀,把正确绝对路径也误拦。绝对化后所有派生根一致绝对、
        # [目录] 提示也变绝对。只在此生产入口处理——测试直接构造的值不受影响。
        config.runtime.workspace = str(
            Path(config.runtime.workspace).expanduser().resolve())
        # 出站内部调用与入站校验共用一个 secret：部署只配 BIOPILOT_INTERNAL_TOKEN，
        # agent 调 Java 平台端点时自动带上，避免两处配不同值导致 403。
        config.platform.internal_token = (
            config.platform.internal_token
            or os.environ.get("BIOPILOT_INTERNAL_TOKEN", ""))
        return config

    def _load_yaml(self, config_path: str | None) -> None:
        """从可选的 config.yaml 读取配置并覆盖默认值。

        顶层键与 dataclass 字段同名（``llm`` / ``runtime`` / ``rag`` …），
        经通用递归合并 ``_merge`` 下行，任意深度；不存在的文件静默跳过，
        未知键忽略。

        Args:
            config_path: str | None，config.yaml 路径；文件不存在时静默跳过
        """
        path = Path(config_path or "config.yaml")
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return

        _merge(self, data)

    def _load_env(self) -> None:
        """
        从环境变量读取配置并覆盖 YAML / 默认值。

        env 名 = ``BIOPILOT_`` + 配置路径（``.`` 换 ``_``）大写，如
        ``BIOPILOT_LLM_API_KEY`` / ``BIOPILOT_RAG_STORAGE_URI`` /
        ``BIOPILOT_RAG_QUERY_REWRITE_MODEL``。自由 dict/list 字段
        （如 ``agents.timeouts``）不派生 env。
        """
        _apply_env(self, ())


def _apply_env(node, prefix: tuple[str, ...]) -> None:
    """按路径约定递归派生 env 并覆盖：仅标量字段消费 env，dict/list 跳过。

    Args:
        node: 任意 dataclass 实例（被就地覆写）
        prefix: tuple[str, ...]，当前路径前缀（拼 BIOPILOT_* env 名）
    """
    for f in fields(node):
        cur = getattr(node, f.name)
        path = prefix + (f.name,)
        if is_dataclass(cur) and not isinstance(cur, type):
            _apply_env(cur, path)
            continue
        if isinstance(cur, (dict, list)):
            continue  # YAML-only 自由集合
        if not _is_scalar(cur):
            continue  # 非标量自定义对象不派生 env、不覆写
        env_name = "BIOPILOT_" + "_".join(p.upper() for p in path)
        val = os.getenv(env_name)
        if val:
            setattr(node, f.name, _coerce(cur, val))


def user_cache_root(config) -> Path:
    """返回按用户隔离的派生缓存根（附件副本与技能物化目录）。

    内容全部可从 OSS/MySQL 重建，不属于真相源；单独提出来是为了让它能留在
    仓库内，而运行数据根本身重定向到仓库外。

    Args:
        config: BioPilotConfig（读取 ``runtime.user_cache_dir`` 与 ``runtime.workspace``）。

    Returns:
        缓存根目录的绝对路径：配置值优先；空串回退 ``<workspace>/user-cache``；
        相对路径按仓库安装根解析。
    """
    raw = str(getattr(config.runtime, "user_cache_dir", "") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = _INSTALL_ROOT / path
        return path.resolve()
    return (Path(config.runtime.workspace).expanduser() / "user-cache").resolve()
