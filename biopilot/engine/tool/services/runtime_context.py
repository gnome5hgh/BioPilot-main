"""工具运行时上下文：按 run 绑定记忆管理器与 RAG 用户域。

工具不持有会话状态；execute 时经 ``get_memory_context()`` / ``get_rag_domain()``
取当前 run 的上下文。绑定用 **ContextVar**：多用户 web 进程里多个会话的 run 并发
交错，模块级单例会被后装配的会话覆盖（A 的记忆写进 B 的域）；ContextVar 按 asyncio
任务隔离——``Agent.run()`` 入口为本轮任务绑定自己的上下文、finally 复位，嵌套
spawn 的子 agent 各绑各的、退出自动还原。CLI 单会话语义不变（装配期绑定一次，
其后所有任务继承）。

未绑定时 ``get_memory_context()`` 返回 None，工具据此降级（统一回「记忆服务未
装配」而非抛异常）；``get_rag_domain()`` 缺省回 ``local``。这样工具定义与运行时
装配彻底解耦，测试也能传 None 隔离。
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass

__all__ = [
    "MemoryToolsContext",
    "set_memory_context", "reset_memory_context", "get_memory_context",
    "set_rag_domain", "reset_rag_domain", "get_rag_domain",
]


@dataclass
class MemoryToolsContext:
    """记忆工具共享上下文（各工具 execute 时经 get_memory_context() 取得）。

    Attributes:
        agent_id: str，归属会话标识（消息检索/落盘按它键控）
        user_id: str，归属用户（外置键命名空间与行级隔离域）
        block_manager: BlockManager，块 CRUD 服务句柄
        message_manager: MessageManager，对话落盘与检索句柄
        tool_result_store: object | None，大工具结果存档（read_tool_result 用）
        db: MemoryDB | None，库句柄（save_document 等直接落表的工具用）
    """

    agent_id: str = ""
    user_id: str = "local"
    block_manager: object = None
    message_manager: object = None
    tool_result_store: object = None
    db: object = None


_memory_context: contextvars.ContextVar[MemoryToolsContext | None] = (
    contextvars.ContextVar("biopilot_memory_context", default=None))

#: 当前 run 的 RAG 用户域（决定检索/索引进哪个用户的 collection）。
_rag_domain: contextvars.ContextVar[str] = contextvars.ContextVar(
    "biopilot_rag_domain", default="local")


def set_memory_context(ctx: MemoryToolsContext | None):
    """绑定当前任务（及其子任务）的记忆上下文，返回复位令牌。

    调用方若在嵌套场景（run 内 spawn 的子 run）绑定，收尾必须用返回的 token
    调 ContextVar.reset 还原外层绑定；顶层绑定（装配期/单会话进程）可不复位。

    Args:
        ctx: MemoryToolsContext | None，要绑定的上下文；None 清空（测试隔离用）

    Returns:
        contextvars.Token，配对 `get_memory_context` 所在变量的复位令牌。
    """
    return _memory_context.set(ctx)


def reset_memory_context(token) -> None:
    """按 set_memory_context 返回的令牌复位绑定（嵌套 run 退出时还原外层）。

    Args:
        token: set_memory_context 返回的 contextvars.Token。
    """
    _memory_context.reset(token)


def get_memory_context() -> MemoryToolsContext | None:
    """返回当前任务绑定的上下文；未绑定返回 None（工具据此降级）。"""
    return _memory_context.get()


def set_rag_domain(domain: str | None):
    """绑定当前任务（及其子任务）的 RAG 用户域，返回复位令牌。

    Args:
        domain: 用户隔离域（None/空串按 local 处理）。

    Returns:
        contextvars.Token，嵌套场景收尾用 ContextVar.reset 还原外层绑定。
    """
    return _rag_domain.set(domain or "local")


def reset_rag_domain(token) -> None:
    """按 set_rag_domain 返回的令牌复位绑定（嵌套 run 退出时还原外层）。

    Args:
        token: set_rag_domain 返回的 contextvars.Token。
    """
    _rag_domain.reset(token)


def get_rag_domain() -> str:
    """返回当前任务绑定的用户域；未绑定返回 local。"""
    return _rag_domain.get() or "local"
