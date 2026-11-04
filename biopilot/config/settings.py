"""配置加载与派生：默认值 → 数据库 → 配置引导文件 → 环境变量。

优先级从低到高：dataclass 默认值（``sections.py``）→ MySQL 的
``bio_config``（设置页写入的稀疏覆盖）→ ``config.yaml`` 里仅剩的引导层
→ 环境变量（``BIOPILOT_`` + 配置路径大写，``_`` 连接）。

运行时配置的真相源是数据库；``config.yaml`` 只保留「进程启动前必须知道、
且跟部署环境绑定」的引导项（连接串、外部服务地址、本机路径），且可以被环境
变量完全取代。测试与离线脚本通过 ``BIOPILOT_CONFIG_SOURCE=file`` 关闭数据库
读取，回到「默认值 → YAML → env」的旧链路。
"""
import logging
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from biopilot.config.schema import BOOTSTRAP_PATHS, env_name, nest_patches

logger = logging.getLogger(__name__)

#: 仓库安装根（本文件位于 biopilot/config/，向上两级即仓库根）。
#: 相对路径的缓存目录按它解析，避免随启动 cwd 漂移。
_INSTALL_ROOT = Path(__file__).resolve().parents[2]

#: 进程级开关：只有真正的引擎入口（Web 适配层）打开数据库配置源。
#: 测试、评测脚本、一次性运维脚本默认仍走文件链路，不给它们加 MySQL 依赖。
_DB_SOURCE_ENABLED = False


def enable_db_source() -> None:
    """打开数据库配置源（由引擎入口调用；``BIOPILOT_CONFIG_SOURCE=file`` 仍可关闭）。"""
    global _DB_SOURCE_ENABLED
    _DB_SOURCE_ENABLED = True


def db_source_enabled() -> bool:
    """判断当前进程是否应从数据库读取运行时配置。

    ``BIOPILOT_CONFIG_SOURCE`` 显式取值优先：``file`` 恒关闭、``db`` 恒开启；
    未设置时由入口是否调用过 :func:`enable_db_source` 决定。

    Returns:
        bool: 应当读取数据库时返回 True。
    """
    source = os.environ.get("BIOPILOT_CONFIG_SOURCE", "").strip().lower()
    if source == "file":
        return False
    if source == "db":
        return True
    return _DB_SOURCE_ENABLED


def ensure_legacy_import(legacy_path: str | Path | None = None) -> int | None:
    """引擎入口调用：数据库里还没有配置时，把旧 ``config.yaml`` 一次性导入。

    导入后旧文件会被改写成「只含引导层」并留一份 ``.bak``。只由 Web 适配层入口
    调用——普通脚本/测试读配置时**不**触发文件改写。

    Args:
        legacy_path: 旧配置路径；None 时取当前目录的 ``config.yaml``。

    Returns:
        导入后的版本号；没有导入（已有配置 / 文件不存在 / 未启用数据库）时 None。
    """
    if not db_source_enabled():
        return None
    from biopilot.config import store as config_store

    config = BioPilotConfig.from_env()
    path = Path(legacy_path) if legacy_path else Path.cwd() / "config.yaml"
    try:
        return config_store.get_store(
            config.runtime.memory_dsn, config.runtime.workspace
        ).ensure_seeded(path)
    except Exception as exc:  # 数据库不可用不应阻塞启动；错误留给真正需要的链路
        logger.warning("旧配置导入失败，继续使用当前配置：%s", exc)
        return None

from biopilot.config.sections import (
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
        corpus: CorpusConfig，产物路径
        intent: IntentConfig，意图识别
        security: SecurityConfig，安全模块（预批准名单）
        rag: RagConfig，RAG 检索栈
        memory: MemoryConfig，记忆系统
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

    #: 产物路径
    corpus: CorpusConfig = field(default_factory=CorpusConfig)

    #: 意图识别子系统（总开关 + 编码器 + 路由器）
    intent: IntentConfig = field(default_factory=IntentConfig)

    #: 安全模块（外部来源工具的预批准名单 + 可选语义判定层）
    security: SecurityConfig = field(default_factory=SecurityConfig)

    #: RAG 检索栈（嵌入/检索/改写/切块/索引/存储/解析/工具）
    rag: RagConfig = field(default_factory=RagConfig)

    #: 记忆系统（consolidation 后台整合）
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    #: 子 agent 配置（timeouts 为 YAML-only 自由 dict）
    agents: AgentsConfig = field(default_factory=AgentsConfig)

    #: 上下文压缩配置（触发/保留/摘要参数；YAML 与 env 均可覆写）
    compaction: CompactionSettings = field(default_factory=CompactionSettings)

    @classmethod
    def from_env(cls, config_path: str | None = None) -> "BioPilotConfig":
        """工厂方法：按「默认值 → 数据库 → 引导文件 → 环境变量」加载配置。

        显式传入 ``config_path`` 时视为文件模式（测试/离线脚本的旧行为），
        不读取数据库；不传时由进程开关与 ``BIOPILOT_CONFIG_SOURCE`` 决定。

        Args:
            config_path: str | None，YAML 路径；None 时按入口设置选择配置源。

        Returns:
            加载完成的配置（含留空继承与 workspace 绝对化）。
        """
        # 加载 .env 文件（不覆盖已有环境变量，即 OS 环境优先于 .env）
        load_dotenv()

        use_db = config_path is None and db_source_enabled()
        base = cls()
        # 数据库模式下，配置文件只剩引导层；文件模式下仍可整份覆写（兼容测试）。
        base._load_yaml(config_path, allowed_paths=BOOTSTRAP_PATHS if use_db else None)
        base._load_env()   # 先解析出 DSN / workspace，才能去读数据库

        config = cls._load_from_db(base) if use_db else base
        cls._finalize(config)
        return config

    @classmethod
    def _load_from_db(cls, base: "BioPilotConfig") -> "BioPilotConfig":
        """在引导配置之上叠加数据库覆盖；失败时退回引导配置并告警。

        Args:
            base: 已读取引导文件与 env 的配置（提供 DSN 与 workspace）。

        Returns:
            叠加了数据库覆盖的配置；数据库不可用时返回 ``base``。
        """
        from biopilot.config import store as config_store

        dsn = base.runtime.memory_dsn
        workspace = base.runtime.workspace
        try:
            content, secrets, version = config_store.load_cached(dsn, workspace)
            config = cls()
            config._load_yaml(None, allowed_paths=BOOTSTRAP_PATHS)
            if content:
                # 引导层只认 env / 文件，防止历史导入把部署拓扑带进数据库。
                _merge(config, _filter_tree(content, denied=BOOTSTRAP_PATHS))
            if secrets:
                _merge(config, nest_patches(secrets))
            config._load_env()
            return config
        except Exception as exc:  # 数据库不可用不应让配置加载直接炸掉
            logger.warning(
                "数据库配置读取失败，回退到默认值/引导文件/环境变量：%s", exc)
            return base

    @staticmethod
    def _finalize(config: "BioPilotConfig") -> None:
        """归一化派生字段并绝对化路径（所有配置源合并完成后执行一次）。"""
        # trigger/keep 在 YAML 里是裸 dict，_merge 只做整体赋值、不实例化列表元素；
        # 加载完成后归一化成 ContextSize，后续判定才能直接读 .type/.value。
        config.compaction.normalize()
        # 留空继承：rag.query_rewrite ← llm、rag.rerank ← rag.embedding。
        # 必须在全部配置源加载后做——否则 env 覆盖会被继承值抢先顶掉。
        emb = config.rag.embedding
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

    def _load_yaml(self, config_path: str | None,
                   allowed_paths: frozenset[str] | None = None) -> None:
        """从可选的 config.yaml 读取配置并覆盖默认值。

        顶层键与 dataclass 字段同名（``llm`` / ``runtime`` / ``rag`` …），
        经通用递归合并 ``_merge`` 下行，任意深度；不存在的文件静默跳过，
        未知键忽略。

        Args:
            config_path: str | None，config.yaml 路径；文件不存在时静默跳过。
            allowed_paths: 只允许合并这些叶子路径（数据库模式下用于只取引导层）；
                None 表示整份合并。
        """
        path = Path(config_path or "config.yaml")
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return
        if allowed_paths is not None:
            data = _filter_tree(data, allowed=allowed_paths)
        _merge(self, data)

    def _load_env(self) -> None:
        """
        从环境变量读取配置并覆盖 YAML / 默认值。

        env 名 = ``BIOPILOT_`` + 配置路径（``.`` 换 ``_``）大写，如
        ``BIOPILOT_LLM_API_KEY`` / ``BIOPILOT_RAG_STORAGE_URI`` /
        ``BIOPILOT_RAG_QUERY_REWRITE_MODEL``。自由 dict/list 字段
        自由 dict/list 字段（如 ``agents.timeouts``）不派生 env。

        另外兼容部署约定的 ``BIOPILOT_MEMORY_MYSQL_DSN``：它同时被 MemoryDB 与
        start.sh/compose 使用，因此视作 ``runtime.memory_dsn`` 的规范来源；
        显式的 ``BIOPILOT_RUNTIME_MEMORY_DSN`` 优先级更高。
        """
        _apply_env(self, ())
        if (not os.environ.get("BIOPILOT_RUNTIME_MEMORY_DSN")
                and os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN")):
            self.runtime.memory_dsn = os.environ["BIOPILOT_MEMORY_MYSQL_DSN"]


def _filter_tree(data: dict, allowed: frozenset[str] | None = None,
                 denied: frozenset[str] | None = None,
                 prefix: tuple[str, ...] = ()) -> dict:
    """按叶子路径白名单/黑名单裁剪嵌套配置树。

    ``allowed`` 与 ``denied`` 二选一：前者只保留命中的叶子，后者剔除命中的叶子；
    未命中的中间对象继续递归，子节点被裁空的整段丢弃。

    Args:
        data: 嵌套配置字典。
        allowed: 允许保留的叶子路径集合；None 表示不按白名单过滤。
        denied: 需要剔除的叶子路径集合；None 表示不按黑名单过滤。
        prefix: 当前路径前缀。

    Returns:
        dict: 裁剪后的新字典（不修改入参）。
    """
    result: dict = {}
    for key, value in data.items():
        path = ".".join(prefix + (str(key),))
        if allowed is not None and path in allowed:
            result[key] = value
            continue
        if denied is not None and path in denied:
            continue
        if isinstance(value, dict):
            child = _filter_tree(value, allowed, denied, prefix + (str(key),))
            if child:
                result[key] = child
        elif allowed is None:
            result[key] = value
    return result


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
        env_name_full = env_name(".".join(path))
        val = os.getenv(env_name_full)
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
