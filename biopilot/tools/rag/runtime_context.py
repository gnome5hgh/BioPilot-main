"""RAG 工具运行时域绑定：检索/索引按当前 run 的用户域隔离。

工具不持有用户身份；execute 时经 get_rag_domain() 取当前绑定的隔离域（缺省
local）。绑定发生在 Agent.run() 入口（与记忆工具上下文同一机制）：多用户 web
进程里多个会话并发交错，ContextVar 按 asyncio 任务隔离——每个 run 各绑各的
域，检索面与索引进的是本人的 collection；REPL 单机恒 local，语义不变。
"""
from __future__ import annotations

import contextvars

__all__ = ["set_rag_domain", "reset_rag_domain", "get_rag_domain"]

_rag_domain: contextvars.ContextVar[str] = contextvars.ContextVar(
    "biopilot_rag_domain", default="local")


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
