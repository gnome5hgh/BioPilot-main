"""Web 会话装配实现：把配置、记忆、安全、意图与工具组装成 supervisor。"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from biopilot.config import BioPilotConfig, user_cache_root
from biopilot.domain.web_session import WebSession
from biopilot.engine.agent import Agent, AgentRegistry
from biopilot.engine.intent.rules.taxonomy import TaxonomyError, load_taxonomy
from biopilot.engine.intent.services.jev import JevClient, JevUnavailable
from biopilot.engine.intent.services.service import IntentService
from biopilot.engine.llm import LLMClient, StructuredOutput
from biopilot.engine.memory.services.agent_manager import AgentManager
from biopilot.engine.memory.services.block_manager import BlockManager
from biopilot.engine.memory.services.consolidation import (
    ConsolidationQueue,
    MemoryConsolidator,
)
from biopilot.engine.memory.services.message_manager import MessageManager
from biopilot.engine.memory.storage.database import MemoryDB
from biopilot.engine.security import (
    AuditMiddleware,
    CommandGuardMiddleware,
    ContentGuardMiddleware,
    PolicyEngineMiddleware,
)
from biopilot.engine.security.services.classifier import build_classifier
from biopilot.engine.skills import (
    SkillRegistry,
    apply_pre_approval,
    merge_tools,
    sync_user_skills,
)
from biopilot.engine.tool.services.offload import make_tool_result_offloader
from biopilot.engine.tool.services.runtime_context import (
    MemoryToolsContext,
    set_memory_context,
)
from biopilot.engine.tool.services.tool_result_store import make_tool_result_store
from biopilot.service import state
from biopilot.service.assembly_service import AssemblyService
from biopilot.tools.skills.load_skill import LoadSkillTool

logger = logging.getLogger(__name__)


#: 平台内部客户端单例：技能物化每次会话都要取包，复用同一个 httpx 客户端。
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
    """预批准的工具名集合，来自 ``security.pre_approved_tools``。"""
    return set(config.security.pre_approved_tools or [])


class AssemblyServiceImpl(AssemblyService):
    """按用户与会话装配一次 supervisor。"""

    async def assemble(self, user_id: str, conversation_id: str,
                       config=None, confirm_callback=None,
                       project_id: str | None = None,
                       model_name: str | None = None) -> WebSession:
        """按用户与会话装配一次 supervisor，供 Web 适配层缓存复用。

        Args:
            user_id: 归属用户（SpringBoot 内网调用携带，即真相）。
            conversation_id: 会话标识（窗口与落盘键控；不存在则创建）。
            config: BioPilotConfig；None 时 from_env。
            confirm_callback: async (ConfirmRequired) -> bool 的确认回调。
            project_id: 归属项目（仅新会话生效）。
            model_name: 会话级模型名。

        Returns:
            WebSession（agent + consolidation_queue）。
        """
        config = config or BioPilotConfig.from_env()

        db = MemoryDB(config.runtime.memory_dsn)
        block_manager = BlockManager(db, user_id=user_id)
        block_manager.migrate_legacy_labels()
        block_manager.purge_removed_blocks()
        block_manager.ensure_default_blocks()
        message_manager = MessageManager(db)
        agent_manager = AgentManager(db, block_manager, message_manager)
        message_manager.agent_manager = agent_manager

        # 会话：同用户存在则复用（回续语义），不存在则创建；他人占用即拒绝
        try:
            agent_state = agent_manager.get_agent(conversation_id, user_id=user_id)
        except KeyError:
            agent_state = agent_manager.create_agent(
                conversation_id, user_id=user_id, project_id=project_id)

        # 会话级模型选择：条目字段覆盖主模型配置（缺省字段回落主 llm 段）
        llm_cfg = config.llm
        if model_name:
            entry = config.runtime.find_model_entry(model_name)
            if entry is not None:
                llm_cfg = replace(
                    config.llm,
                    model=entry.get("model", config.llm.model),
                    base_url=entry.get("base_url", config.llm.base_url),
                    api_key=entry.get("api_key", config.llm.api_key))
        llm = LLMClient(llm_cfg)
        agents_dir = (config.runtime.agents_dir
                      if Path(config.runtime.agents_dir).is_dir()
                      else str(Path(__file__).resolve().parents[3] / "agents"))
        registry = AgentRegistry(agents_dir)

        # Skill 体系装配：只物化当前用户的技能缓存（平台 OSS 是内容真相）
        _user_cache = None
        try:
            _platform = _shared_platform_client(config)
            _user_cache = await asyncio.to_thread(
                sync_user_skills, db, _platform, str(user_cache_root(config)),
                user_id)
        except Exception:
            logger.warning("用户技能物化失败，本次会话不加载额外技能（%s）", user_id,
                           exc_info=True)
        skill_registry = SkillRegistry(
            str(_user_cache) if _user_cache is not None else None)
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
            summary_llm = LLMClient(
                replace(config.llm, model=config.compaction.summary_model_name))
            summary_structured = StructuredOutput(summary_llm)

        tool_result_store = make_tool_result_store(config)
        tool_result_offloader = make_tool_result_offloader(
            tool_result_store, config.compaction.tool_results)

        # 会话级记忆工具上下文：装配期 set，并随 Agent 持有
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
            ContentGuardMiddleware(classifier=build_classifier(config)),
            CommandGuardMiddleware(),
            PolicyEngineMiddleware(confirm_above=config.runtime.confirm_above),
        ]

        # 意图层（可选）：判定服务不可达则整层不装配
        intent_service = None
        if config.intent.enabled:
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

    async def default_agent_factory(self, user_id: str, conversation_id: str,
                                    confirm_callback=None,
                                    project_id: str | None = None):
        """真实装配：装配一次 Web 会话并登记整合队列。"""
        session = await self.assemble(
            user_id, conversation_id,
            confirm_callback=confirm_callback,
            project_id=project_id,
            model_name=state.user_models.get(user_id))
        session.agent._consolidation_queue = session.consolidation_queue
        state._queues[(user_id, conversation_id)] = session.consolidation_queue
        return session.agent


_service = AssemblyServiceImpl()


async def assemble_web_session(user_id: str, conversation_id: str, config=None,
                               confirm_callback=None,
                               project_id: str | None = None,
                               model_name: str | None = None) -> WebSession:
    """兼容旧导入路径的模块级装配函数。"""
    return await _service.assemble(
        user_id, conversation_id, config=config,
        confirm_callback=confirm_callback, project_id=project_id,
        model_name=model_name)
