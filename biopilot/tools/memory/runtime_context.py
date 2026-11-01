"""记忆工具运行时上下文 + 模块级访问器。

工具不持有上下文；execute 时经 get_memory_context() 取运行时绑定的 managers
与归属会话。绑定用 **ContextVar**：多用户 web 进程里多个会话的 run 并发交错，
模块级单例会被后装配的会话覆盖（A 的记忆写进 B 的域）；ContextVar 按 asyncio
任务隔离——Agent.run() 入口为本轮任务绑定自己的上下文、finally 复位，嵌套
spawn 的子 agent 各绑各的、退出自动还原。CLI 单会话语义不变（装配期绑定一次，
其后所有任务继承）。未绑定返回 None，工具据此降级（统一回「记忆服务未装配」
而非抛异常）——工具定义与服务装配彻底解耦，测试也能传 None 隔离。
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass

__all__ = ["MemoryToolsContext", "set_memory_context",
           "reset_memory_context", "get_memory_context"]


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


def set_memory_context(ctx: MemoryToolsContext | None):
    """绑定当前任务（及其子任务）的记忆上下文，返回复位令牌。

    调用方若在嵌套场景（run 内 spawn 的子 run）绑定，收尾必须用返回的 token
    调 ContextVar.reset 还原外层绑定；顶层绑定（装配期/单会话 REPL）可不复位。

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
