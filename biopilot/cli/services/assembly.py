"""装配组合根：把配置、记忆、安全、意图、工具与终端装配成一个可运行的 REPL。

装配顺序与依赖方向见 `main()` 的 docstring；启动预检在 `bootstrap.py`。
"""
import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from rich.console import Console

from biopilot.cli.services.bootstrap import _ensure_services

logger = logging.getLogger(__name__)
from biopilot.config import BioPilotConfig, user_cache_root
from biopilot.core.agent import Agent
from biopilot.core.agent import AgentRegistry
from biopilot.core.skills import (
    SkillRegistry,
    apply_pre_approval,
    merge_tools,
    sync_user_skills,
)
from biopilot.tools.skills.load_skill import LoadSkillTool
from biopilot.core.tool.services.roots import declared_roots
from biopilot.core.llm import LLMClient
from biopilot.core.security.services.classifier import build_classifier
from biopilot.core.security import (
    AuditMiddleware, WorkspacePolicyMiddleware,
    ContentGuardMiddleware, CommandGuardMiddleware, PolicyEngineMiddleware,
)
from biopilot.core.llm import StructuredOutput
from biopilot.core.tool.services.offload import make_tool_result_offloader
from biopilot.core.tool.services.tool_result_store import make_tool_result_store
from biopilot.core.memory.storage.database import MemoryDB
from biopilot.core.memory.services.block_manager import BlockManager
from biopilot.core.memory.services.message_manager import MessageManager
from biopilot.core.tool.services.runtime_context import (
    set_memory_context, MemoryToolsContext)
from biopilot.core.memory.services.agent_manager import AgentManager
from biopilot.core.memory.services.consolidation import MemoryConsolidator
from biopilot.core.memory.services.consolidation import ConsolidationQueue
from biopilot.core.intent.services.jev import JevClient, JevUnavailable
from biopilot.core.intent.services.service import IntentService
from biopilot.core.intent.rules.taxonomy import TaxonomyError, load_taxonomy
from biopilot.terminal.confirm import ConfirmCenter, _make_confirm_callback
from biopilot.terminal.io import make_input_io
from biopilot.terminal.render import make_renderer
from biopilot.terminal.repl import _repl, _make_print_fn
from biopilot.terminal.repl import build_resume_replay


#: 平台内部客户端单例：技能物化每次会话都要取包，复用同一个 httpx 客户端，
#: 避免每个会话都新建连接池；部署地址在进程生命周期内不变。
_PLATFORM_CLIENT: object | None = None


def _shared_platform_client(config: BioPilotConfig):
    """返回进程级共享的平台内部客户端（懒建单例）。

    Args:
        config: 引擎配置（决定平台地址与内部 token）。

    Returns:
        PlatformClient 单例。
    """
    global _PLATFORM_CLIENT
    if _PLATFORM_CLIENT is None:
        from biopilot.common.platform import make_platform_client
        _PLATFORM_CLIENT = make_platform_client(config)
    return _PLATFORM_CLIENT


def _approved_tools(config: BioPilotConfig) -> set[str]:
    """预批准的工具名集合，来自 ``security.pre_approved_tools``。

    Args:
        config: BioPilotConfig，配置来源

    Returns:
        set[str]，允许降档（medium）的工具名集合。
    """
    return set(config.security.pre_approved_tools or [])


def _select_resume_session(agent_manager: AgentManager, io, user_id: str) -> str | None:
    """列出历史会话并让用户选择要恢复的会话（`--resume` 不带 id 时）。

    Args:
        agent_manager: 记忆服务层句柄（读 bio_agent_state / bio_message 表）。
        io: 输入适配器（读用户选择）。
        user_id: 归属域（本机单人恒 local；Web 终端注入登录用户 id）。

    Returns:
        选中的 session_id；取消（空输入）或无历史会话时返回 None。

    选择方式：输入菜单编号，或直接粘贴会话 id。非法输入返回 None 并打印原因。
    """
    sessions = agent_manager.list_sessions(limit=10, user_id=user_id)
    if not sessions:
        print("没有可恢复的历史会话。")
        return None
    print("历史会话（新→旧）：")
    for i, s in enumerate(sessions, 1):
        print(f"  {i}. [{s['created_at'][:19]}] {s['agent_id']}"
              f"（{s['message_count']} 条消息）{s['preview']}")
    try:
        raw = io.read("输入编号恢复（回车取消）：").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(sessions):
        return sessions[int(raw) - 1]["agent_id"]
    if any(s["agent_id"] == raw for s in sessions):
        return raw
    print(f"无效选择：{raw}")
    return None


@dataclass
class WebSession:
    """web 会话装配产物（适配层持有：run 用 Agent，收尾用整合队列）。

    Attributes:
        agent: 装配完成的 supervisor。
        consolidation_queue: 每轮收尾的整合队列（跑在适配层事件循环上）。
    """

    agent: object
    consolidation_queue: object


async def assemble_web_session(user_id: str, conversation_id: str,
                               config=None, confirm_callback=None,
                               project_id: str | None = None,
                               model_name: str | None = None) -> WebSession:
    """Web 适配层的会话装配：与 main() 同一套对象图，无终端 IO。

    与 main() 的三处差异（业务层替换的边界内）：
        - 用户域按 user_id（适配层透传，内网带入即真相）；REPL 恒 "local"。
        - 确认回调 fail-safe 拒绝（Web 确认通道接好后替换为真实往返）。
        - 服务预检跳过（compose 服务由部署层保证；不可达按软依赖降级）。

    Args:
        user_id: 归属用户（SpringBoot 内网调用携带，即真相）。
        conversation_id: 会话标识（窗口与落盘键控；不存在则创建）。
        config: BioPilotConfig；None 时 from_env。
        confirm_callback: async (ConfirmRequired) -> bool 的确认回调；None 时
            fail-safe 拒绝（Web 适配层传入 SSE 往返实现）。
        project_id: 归属项目（仅新会话生效；已有会话不挪组）。

    Returns:
        WebSession（agent + consolidation_queue）。
    """
    from biopilot.core.agent import Agent
    from biopilot.core.llm import LLMClient, StructuredOutput
    from biopilot.core.memory.services.agent_manager import AgentManager
    from biopilot.core.memory.services.block_manager import BlockManager
    from biopilot.core.memory.services.consolidation import MemoryConsolidator
    from biopilot.core.memory.services.consolidation import ConsolidationQueue
    from biopilot.core.memory.services.message_manager import MessageManager
    from biopilot.core.memory.storage.database import MemoryDB
    from biopilot.core.security.middleware.audit import AuditMiddleware
    from biopilot.core.security.middleware.command_guard import CommandGuardMiddleware
    from biopilot.core.security.middleware.content_guard import ContentGuardMiddleware
    from biopilot.core.security.middleware.policy_engine import PolicyEngineMiddleware
    # WorkspacePolicyMiddleware 不在此处再导入：模块顶部已从包门面导入（文件名是 workspace.py）

    config = config or BioPilotConfig.from_env()

    db = MemoryDB(config.runtime.memory_dsn)
    block_manager = BlockManager(db, user_id=user_id)
    block_manager.migrate_legacy_labels()
    block_manager.purge_removed_blocks()
    block_manager.ensure_default_blocks()
    message_manager = MessageManager(db)
    agent_manager = AgentManager(db, block_manager, message_manager)
    message_manager.agent_manager = agent_manager

    # 会话：同用户存在则复用（回续语义），不存在则创建；他人占用即拒绝——
    # conversation_id 由客户端生成，必须验证归属才允许读到既有上下文
    try:
        agent_state = agent_manager.get_agent(conversation_id, user_id=user_id)
    except KeyError:
        agent_state = agent_manager.create_agent(conversation_id, user_id=user_id,
                                                 project_id=project_id)

    # 会话级模型选择：条目字段覆盖主模型配置（缺省字段回落主 llm 段）
    llm_cfg = config.llm
    if model_name:
        entry = config.runtime.find_model_entry(model_name)
        if entry is not None:
            from dataclasses import replace as _dc_replace
            llm_cfg = _dc_replace(
                config.llm,
                model=entry.get("model", config.llm.model),
                base_url=entry.get("base_url", config.llm.base_url),
                api_key=entry.get("api_key", config.llm.api_key))
    llm = LLMClient(llm_cfg)
    agents_dir = (config.runtime.agents_dir if Path(config.runtime.agents_dir).is_dir()
                  else str(Path(__file__).resolve().parents[3] / "agents"))
    registry = AgentRegistry(agents_dir)

    # Skill 体系装配：只物化当前用户的技能缓存（平台 OSS 是内容真相，本地只是副本）。
    # 平台不可达时保留旧缓存继续用；没有缓存则该用户暂时没有额外技能，不阻塞对话。
    _user_cache = None
    try:
        _platform = _shared_platform_client(config)
        _user_cache = await asyncio.to_thread(
            sync_user_skills, db, _platform, str(user_cache_root(config)), user_id)
    except Exception:
        logger.warning("用户技能物化失败，本次会话不加载额外技能（%s）", user_id,
                       exc_info=True)
    skill_registry = SkillRegistry(str(_user_cache) if _user_cache is not None else None)
    _load_skill_tool = LoadSkillTool(skill_registry)
    for _agent_type in registry.list_agents():
        _cfg = registry.get_config(_agent_type)
        _cfg.tools = merge_tools(
            ("agent", _cfg.tools),
            ("framework", [_load_skill_tool]),
        )
        apply_pre_approval(_cfg.tools, _approved_tools(config))

    structured = StructuredOutput(llm)
    summary_structured = None
    if config.compaction.summary_model_name:
        from dataclasses import replace as _replace
        summary_llm = LLMClient(_replace(config.llm, model=config.compaction.summary_model_name))
        summary_structured = StructuredOutput(summary_llm)

    tool_result_store = make_tool_result_store(config)
    tool_result_offloader = make_tool_result_offloader(
        tool_result_store, config.compaction.tool_results)

    # 会话级记忆工具上下文：装配期 set（兼容单会话语义），并随 Agent 持有——
    # run 入口经 ContextVar 绑定，多会话进程里各 Agent 互不覆盖
    memory_ctx = MemoryToolsContext(
        agent_id=conversation_id,
        user_id=user_id,
        block_manager=block_manager,
        message_manager=message_manager,
        tool_result_store=tool_result_store,
        db=db,
    )
    set_memory_context(memory_ctx)

    middlewares = [
        AuditMiddleware(db=db),
        WorkspacePolicyMiddleware(workspace=config.runtime.workspace,
                                  write_roots=declared_roots(config)),
        ContentGuardMiddleware(classifier=build_classifier(config)),
        CommandGuardMiddleware(),
        PolicyEngineMiddleware(confirm_above=config.runtime.confirm_above),
    ]

    # 意图层（可选）：web 路径与 REPL 同策略——判定服务不可达则整层不装配。
    # IntentService/load_taxonomy/TaxonomyError 顶部已导入，此处只补 Jev 异常。
    intent_service = None
    if config.intent.enabled:
        from biopilot.core.intent.services.jev import JevUnavailable
        try:
            taxonomy = load_taxonomy()
        except TaxonomyError as exc:
            raise RuntimeError(f"意图识别已启用，但知识库装载失败：{exc}") from exc
        judge = JevClient(config.intent.jev.base_url, config.intent.jev.api_key,
                          config.intent.jev.model,
                          timeout=config.intent.jev.timeout,
                          max_retries=config.intent.jev.max_retries,
                          zero_data_retention=config.intent.jev.zero_data_retention,
                          only_provider=config.intent.jev.only_provider)
        try:
            # 装配运行在事件循环内的协程里，probe 是 async——asyncio.run 会直接抛错
            await judge.probe()
        except JevUnavailable as exc:
            logger.warning("意图判定服务不可用，web 会话走纯 ReAct: %s", exc.reason)
        else:
            intent_service = IntentService(
                taxonomy=taxonomy, judge=judge,
                history_messages=config.intent.history_messages)

    async def _fail_safe_confirm(req) -> bool:
        # 无确认回调时的兜底：拒绝（确认永不静默放行）
        logger.warning("确认请求无回调，fail-safe 拒绝：%s", req)
        return False
    _web_confirm_callback = confirm_callback or _fail_safe_confirm

    agent = Agent(
        llm=llm, agent_registry=registry, agent_type="supervisor",
        skill_registry=skill_registry,
        memory=agent_state.memory,
        agent_manager=agent_manager, block_manager=block_manager,
        message_manager=message_manager,
        compaction=config.compaction,
        structured=structured,
        summary_structured=summary_structured,
        offloader=tool_result_offloader,
        security_middleware=middlewares,
        intent_service=intent_service,
        confirm_callback=_web_confirm_callback,
        session_id=conversation_id,
        user_id=user_id,
        memory_context=memory_ctx
    )
    consolidator = MemoryConsolidator(
        agent_state, block_manager, message_manager,
        structured, enable=config.memory.consolidation_enabled)
    consolidation_queue = ConsolidationQueue(
        consolidator, conversation_id,
        debounce_seconds=config.memory.debounce_seconds,
        max_delay_seconds=config.memory.max_delay_seconds)
    return WebSession(agent=agent, consolidation_queue=consolidation_queue)


def main(argv: list[str] | None = None) -> int | None:
    """装配全部依赖并启动 REPL。


    Returns:
        无参 REPL 路径返回 None（REPL 正常退出即成功）。


    命令行参数（argparse）：
        --help：用法。
        --resume [SESSION_ID]：恢复历史会话；不带 id 时列出历史会话供选择。
        --skip-bootstrap：跳过依赖服务启动预检（等价 BIOPILOT_SKIP_BOOTSTRAP=1）。
    无参数行为与历史版本完全一致：装配后进入新会话 REPL。

    装配顺序（依赖关系）：
        1. 终端 IO 和渲染器（输入/输出适配）。
        2. 会话 ID（用于记忆服务键控；--resume 时复用已落盘会话）。
        3. 记忆服务层：DB → BlockManager → MessageManager → AgentManager。
        4. 意图编码器（云端实例）注入 MessageManager。
        5. AgentManager 回填到 MessageManager（用于读取 AgentState）。
        6. 创建 AgentState 和结构化输出。
        7. 设置记忆工具上下文。
        8. 构造安全中间件、意图管线。
        9. 构造 Supervisor Agent 和 MemoryConsolidator。
        10. 运行 REPL 主循环。

    关键依赖顺序：
        - AgentManager 依赖 BlockManager 和 MessageManager；MessageManager 需要 AgentManager 来获取 in-context 窗口，
          因此创建顺序为：先建 AgentManager，再回填 MessageManager.agent_manager。

    Args:
        argv: list[str] | None，命令行参数（None 时读 sys.argv）
    """
    import argparse

    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] == "config":
        from biopilot.cli.services.config_cli import config_main
        return config_main(raw_args[1:])

    parser = argparse.ArgumentParser(
        prog="biopilot",
        description="BioPilot 学术研究工作流助手（交互式 REPL，自然语言即命令）",
        epilog="配置管理：biopilot config import|export|history|rollback")
    parser.add_argument("--resume", nargs="?", const="", default=None,
                        metavar="SESSION_ID",
                        help="恢复历史会话；不带 id 则列出历史会话供选择")
    parser.add_argument("--web", action="store_true", dest="web",
                        help="启动 Web 适配层（本地 HTTP/SSE 服务）而非 REPL")
    parser.add_argument("--skip-bootstrap", action="store_true",
                        help="跳过依赖服务（Milvus）启动预检")
    args = parser.parse_args(argv)
    if getattr(args, "web", False):
        # Web 适配层：SSE 服务。DSN 经环境变量读取。
        from biopilot.webapi import run_server, WebConfig
        import os as _os
        run_server(WebConfig(
            host=_os.environ.get("BIOPILOT_WEB_HOST", "127.0.0.1"),
            port=int(_os.environ.get("BIOPILOT_WEB_PORT", "8300")),
            memory_dsn=_os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN")))
        return 0

    # 引擎入口才启用数据库配置源：测试与离线脚本默认仍走配置文件。
    from biopilot.config import enable_db_source, ensure_legacy_import
    enable_db_source()
    # 首次部署：把旧的 config.yaml 一次性导入（之后文件只剩引导层）。
    ensure_legacy_import()
    config = BioPilotConfig.from_env()
    is_tty = sys.stdin.isatty()
    io = make_input_io(config)
    console = Console() if is_tty else None
    # 启动预检：依赖服务（Milvus）未起时自动 docker compose 拉起（仅 TTY，
    # 管道/CI 跳过）。软依赖：任何失败只产出警告不阻塞——服务缺席时 RAG/PDF 降级。
    service_warnings = _ensure_services(
        config, is_tty=is_tty, skip=args.skip_bootstrap,
        notify=(lambda msg: console.print(msg, style="dim")) if console else None)
    for w in service_warnings:
        (console.print(w, style="yellow") if console else print(w))
    # REPL 用户域：本机单人恒 "local"；Web 终端经适配层注入登录用户 id——
    # 终端里的会话与该用户网页会话同库同域，出现在同一任务列表。
    import os as _uid_os
    repl_user = _uid_os.environ.get("BIOPILOT_USER_ID") or "local"

    # api_key 缺失提示：RAG 的云端嵌入未配 key 时只提示不阻断（检索退纯
    # BM25、无精排，降级路径由 retriever 自己消化）。
    if not config.rag.embedding.api_key:
        _msg = ("未配置云端嵌入 api_key（设置页 → 检索增强 → 嵌入）："
                "RAG 检索无稠密路与精排。"
                "注册 siliconflow.cn 获取（含实名认证）。")
        (console.print(_msg, style="yellow") if console else print(_msg))
    try:
        llm = LLMClient(config.llm)
    except RuntimeError as e:
        # 未配置 API key：用户语言的红字提示，不再是裸 traceback
        (console.print(f"[red]{e}[/red]") if console else print(f"错误：{e}"))
        sys.exit(1)
    # agents 插件目录：配置路径不存在时回退安装根（从非仓库目录启动也能找到插件；
    # 与 _find_compose_dir 的「cwd 优先、安装根回退」同一模式）
    agents_dir = (config.runtime.agents_dir if Path(config.runtime.agents_dir).is_dir()
                  else str(Path(__file__).resolve().parents[3] / "agents"))
    registry = AgentRegistry(agents_dir)

    # Skill 体系装配：REPL 是开发工具，不接平台用户技能（空注册表，load_skill 仍存在）。
    skill_registry = SkillRegistry(None)
    # load_skill 无可见性门控（skill 对所有 agent 可见），也不持有父 Agent 引用，
    # 因此全进程共享一个实例即可被所有 agent 安全复用。
    _load_skill_tool = LoadSkillTool(skill_registry)
    for _agent_type in registry.list_agents():
        _cfg = registry.get_config(_agent_type)
        _cfg.tools = merge_tools(
            ("agent", _cfg.tools),
            ("framework", [_load_skill_tool]),
        )
        apply_pre_approval(_cfg.tools, _approved_tools(config))

    # 终端装配：TTY → prompt_toolkit 输入 + rich Live 渲染；非 TTY（管道/CI/测试）→
    # FallbackIO + PlainBlock 降级。renderer 须在 supervisor 前构造——confirm_callback
    # （写/编辑确认 diff 预览）是 supervisor 构造参数。
    # root_agent_type 恒为 "supervisor"（根 agent 的 agent_type 见 supervisor 构造处）。
    renderer = make_renderer(
        _make_print_fn(console),
        "supervisor",
        is_tty=is_tty, console=console,
    )

    # 会话标识：本次进程启动即一个会话；--resume 时复用已落盘会话 id。
    # AgentManager.create_agent 的 agent_id 与 Agent.session_id 必须一致——
    # 记忆工具（SQL 按 agent_id 键控）与 MemoryConsolidator 都挂在它下面，三者对不上
    # 会各自读到空数据。
    db = MemoryDB(config.runtime.memory_dsn)
    block_manager = BlockManager(db, user_id=repl_user)
    block_manager.migrate_legacy_labels()   # 旧 human/persona label 一次性迁移为 profile/assistant（幂等）
    block_manager.purge_removed_blocks()    # 已下线功能的块（历史清单）一次性清除（幂等）
    block_manager.ensure_default_blocks()   # 首启播种默认 profile/assistant 核心记忆块
    message_manager = MessageManager(db)
    agent_manager = AgentManager(db, block_manager, message_manager)

    resume_hint: str | None = None
    if args.resume is not None:
        if args.resume:
            # 带 id：会话必须存在，否则给出友好列表后退出
            try:
                agent_manager.get_agent(args.resume)
            except KeyError:
                print(f"未找到会话 {args.resume}。可运行 `biopilot --resume` 查看历史会话列表。")
                sys.exit(1)
            session_id = args.resume
        else:
            session_id = _select_resume_session(agent_manager, io, user_id=repl_user)
            if session_id is None:
                sys.exit(0)
    else:
        session_id = uuid.uuid4().hex[:8]
        # 无参启动保持新会话；检测到历史会话时提示可恢复（不自动询问）
        last = agent_manager.list_sessions(limit=1, user_id=repl_user)
        if last and last[0]["message_count"] > 0:
            preview = last[0]["preview"] or "（无预览）"
            resume_hint = f"检测到上次会话（{preview}），biopilot --resume 可恢复"

    # MessageManager 经 agent_manager 读 AgentState.message_ids（in-context 窗口），
    # 压缩后的摘要/尾部要跨轮回放——装配顺序上 agent_manager 后置，故在此回填。
    message_manager.agent_manager = agent_manager
    if args.resume is not None:
        agent_state = agent_manager.get_agent(session_id)
    else:
        agent_state = agent_manager.create_agent(session_id, user_id=repl_user)

    # 会话恢复的历史回放：--resume 恢复的是模型上下文，屏幕上
    # 否则不留任何痕迹，用户会以为恢复失败。这里把**同一个** in-context 窗口投影成
    # 回放载荷（数据源与模型一致），由 _repl 在横幅之后渲染进滚动区。
    # 必须在此处（message_manager.agent_manager 回填之后）构建：否则
    # get_in_context_messages 读不到窗口，会降级成全量查询、与模型所见不一致。
    resume_replay = None
    if args.resume is not None and config.session.resume_replay:
        resume_replay = build_resume_replay(
            message_manager, session_id, limit=config.session.resume_replay_limit,
            created_at=(str(agent_state.created_at)[:16]
                        if agent_state.created_at else None))

    structured = StructuredOutput(llm)

    # 摘要专用模型：配置了 compaction.summary_model_name 时另建一个结构化输出，
    # 让压缩摘要走轻量端点；未配置则沿用主模型。
    summary_structured = None
    if config.compaction.summary_model_name:
        summary_llm = LLMClient(
            replace(config.llm, model=config.compaction.summary_model_name))
        summary_structured = StructuredOutput(summary_llm)

    # 大工具结果外置：原文进对象存储（本地回退），消息里只留指针。
    tool_result_store = make_tool_result_store(config)
    tool_result_offloader = make_tool_result_offloader(
        tool_result_store, config.compaction.tool_results)

    memory_ctx = MemoryToolsContext(
        agent_id=session_id,
        user_id=repl_user,
        block_manager=block_manager,
        message_manager=message_manager,
        tool_result_store=tool_result_store,
        db=db,
    )
    set_memory_context(memory_ctx)

    # 安全管道：五个中间件（经验记忆中间件已移除——工具调用经验不再注入 prompt，
    # 改由 MemoryConsolidator 后台整合进核心记忆块）。
    middlewares = [
        # 审计事件 insert-only 落 MySQL（bio_security_audit_event），不依赖工作区目录
        AuditMiddleware(db=db),
        # write_roots = 已声明的产物根 + 工作区：写目标落在其外时升级确认
        WorkspacePolicyMiddleware(workspace=config.runtime.workspace,
                                  write_roots=declared_roots(config)),
        # 语义判定层按配置构造：未启用或缺端点即 None（整层不装配）
        ContentGuardMiddleware(classifier=build_classifier(config)),
        # 命令防护：零工具声明 format="shell_command" 时是纯 no-op（为将来的 shell 工具留的缝）
        CommandGuardMiddleware(),
        PolicyEngineMiddleware(confirm_above=config.runtime.confirm_above),
    ]

    # 意图识别装配（可选预处理层）：关时整段跳过——不装载知识库、不探测判定服务，
    # supervisor 走纯 ReAct。开启要过两道：① 知识库能装载（类别缺条目、规则指向未知
    # 类别这类问题在这里就炸掉，fail-closed）；② 判定服务可达（网关是托管 API，
    # 账户未绑卡一律 403）。**判定服务不可达则整套意图层不装配**——只有规则层能判的
    # 那一小部分不值得挂着一个「大部分请求没有提示」的半层。
    intent_service = None
    if config.intent.enabled:
        try:
            taxonomy = load_taxonomy()
        except TaxonomyError as exc:
            # 知识库坏了是配置/数据错误（类别与枚举对不上、规则写错），
            # 必须人去改——fail-closed 拒绝启动，但给一行能读懂的话而不是 traceback。
            _msg = f"意图识别已启用，但知识库装载失败：{exc}"
            (console.print(_msg, style="red") if console else print(_msg))
            sys.exit(1)
        judge = JevClient(config.intent.jev.base_url, config.intent.jev.api_key,
                          config.intent.jev.model,
                          timeout=config.intent.jev.timeout,
                          max_retries=config.intent.jev.max_retries,
                          zero_data_retention=config.intent.jev.zero_data_retention,
                          only_provider=config.intent.jev.only_provider)
        try:
            asyncio.run(judge.probe())
        except JevUnavailable as exc:
            _msg = (f"意图识别已启用，但判定服务不可用：{exc.reason}\n"
                    "  本轮起意图层不装配（supervisor 走纯 ReAct，行为与关闭意图一致）。"
                    "改好配置或恢复网络后重启生效。")
            (console.print(_msg, style="yellow") if console else print(_msg))
        else:
            intent_service = IntentService(
                taxonomy=taxonomy, judge=judge,
                history_messages=config.intent.history_messages)

    # 确认中心：确认的唯一消费者，跑在 REPL 主事件循环上（启动/收尾在
    # _repl 内）。confirm 回调经它跨线程桥接，弹框期间渲染抑制——并行多
    # agent 的确认框不再被其他 agent 的渲染事件盖掉。
    center = ConfirmCenter(io, renderer)

    supervisor = Agent(
        llm=llm, agent_registry=registry, agent_type="supervisor",
        skill_registry=skill_registry,
        memory=agent_state.memory,
        agent_manager=agent_manager, block_manager=block_manager,
        message_manager=message_manager,
        compaction=config.compaction,
        structured=structured,
        summary_structured=summary_structured,
        offloader=tool_result_offloader,
        security_middleware=middlewares,
        intent_service=intent_service,
        confirm_callback=_make_confirm_callback(io, renderer, center),
        session_id=session_id,
        user_id=repl_user,
        memory_context=memory_ctx,
    )
    consolidator = MemoryConsolidator(
        agent_state, block_manager, message_manager,
        structured, enable=config.memory.consolidation_enabled)
    consolidation_queue = ConsolidationQueue(
        consolidator, session_id,
        debounce_seconds=config.memory.debounce_seconds,
        max_delay_seconds=config.memory.max_delay_seconds)

    asyncio.run(_repl(supervisor,
                      io=io, renderer=renderer, consolidator=consolidator,
                      consolidation_queue=consolidation_queue,
                      config=config, resume_hint=resume_hint,
                      confirm_center=center, resume_replay=resume_replay))
