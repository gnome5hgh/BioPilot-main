"""agent 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块）一律经本文件或包根别名使用 agent：
ReAct 运行时（``Agent``）、注册表、运行期状态容器、事件契约与上下文用量。
agent 本身不连外部世界（模型/记忆/工具都经别的模块的功能面），因此本模块
没有出向实现，只有编排面的公开声明与组装。

``build_agent`` 是唯一的组装入口：构造期注入全部端口实例（模型、注册表、
记忆栈、安全中间件、确认回调……），Agent 不感知任何具体实现。
"""
from biopilot.engine.agent.application.context_usage import context_usage
from biopilot.engine.agent.application.registry import AgentRegistry
from biopilot.engine.agent.application.runtime import Agent, MaxTurnsExceeded
from biopilot.engine.agent.application.state import get_run_state, get_session_state
from biopilot.engine.agent.config import AgentConfig
from biopilot.engine.agent.constants import AgentEventKind
from biopilot.engine.agent.domain import AgentEvent

__all__ = [
    "Agent", "AgentRegistry", "AgentConfig", "AgentEvent", "AgentEventKind",
    "MaxTurnsExceeded", "context_usage", "get_run_state", "get_session_state",
    "build_agent",
]


def build_agent(*, llm, agent_registry: AgentRegistry, agent_type: str,
                security_middleware=None, confirm_callback=None, user_id: str,
                session_id: str | None = None, conversation_id: str | None = None,
                **kwargs) -> Agent:
    """装配一个 Agent（模块对外唯一的组装入口；参数面与 ``Agent`` 构造一致）。

    Args:
        llm: ModelClient 端口实例（对话模型）。
        agent_registry: AgentRegistry（按 agent_type 拉取配置）。
        agent_type: 角色标识（supervisor / 子角色）。
        security_middleware: 安全中间件列表（``security.adapters.build_middlewares`` 产物）。
        confirm_callback: async 确认回调；None 时 fail-safe 拒绝。
        user_id: 归属用户（必填）。
        session_id: 会话标识（跨轮一致）。
        conversation_id: 具体对话标识；None 回退 session_id。
        **kwargs: 其余 ``Agent`` 构造参数（memory/block_manager/message_manager/
            compaction/structured/offloader/intent_service/run_mutex/skill_registry/
            memory_context/trace_id/max_turns/stream_callback/summary_structured）。

    Returns:
        Agent。
    """
    return Agent(llm=llm, agent_registry=agent_registry, agent_type=agent_type,
                 security_middleware=security_middleware,
                 confirm_callback=confirm_callback, user_id=user_id,
                 session_id=session_id, conversation_id=conversation_id, **kwargs)
