"""上下文窗口用量分解（读侧估算，不参与编排决策）。

消费方：`/chat/context-usage` 端点（SessionService）与装配期用量基线快照
（ChatService）。估算与 run() 的真实发送同源——system 消息经
`Agent.system_message()` 同一入口现取（记忆段随之现读），不在此复刻任何
拼装口径；工具 schema 复用构造期预计算结果，窗口消息即 in-context 缓冲。
"""
from __future__ import annotations

import json

from biopilot.engine.agent.application.runtime import Agent

__all__ = ["context_usage"]


def context_usage(agent: Agent) -> dict:
    """计算当前会话的上下文窗口用量分解（同步、不发 LLM 请求）。

    三类口径，与真实请求一一对应：system_prompt = system 消息整体
    （角色定义+基座/意图规则/skills 清单/可派发清单/session_context/记忆，经
    `Agent.system_message()` 同一构建路径估算）；tools_schema 按 function
    calling JSON 估算；messages 按当前 in-context 窗口估算。有 block_manager
    时记忆段按 ReAct 轮内同口径从库现取（一次 DB 读，无写入），估算值等于
    下一次真实发送的内容。窗口上限 = 显式 context_size > 模型窗口（与压缩
    判定同口径）。必须在 window.load() 之后的时点调用才有消息计数（适配层
    对缓存 Agent 调用时窗口已加载）。

    Args:
        agent: Agent 实例——system 消息经 `system_message()` 现取（有
            block_manager 时会随之刷新其 memory 实例，与 ReAct 轮内同口径），
            其余属性（tool_schemas / window / compaction / llm）只读。

    Returns:
        dict: {total, limit, parts: {...}}，parts 键：system_prompt / tools_schema / messages。
    """
    from biopilot.common.utils.tokenization import estimate_text_tokens
    from biopilot.engine.memory.application.compaction import estimate_tokens

    parts: dict[str, int] = {}
    parts["system_prompt"] = estimate_text_tokens(agent.system_message().content)
    parts["tools_schema"] = estimate_text_tokens(
        json.dumps(agent.tool_schemas, ensure_ascii=False))
    parts["messages"] = estimate_tokens(agent.window.messages)
    total = sum(parts.values())
    limit = (agent.compaction.context_size if agent.compaction
             and agent.compaction.context_size else agent.llm.context_window)
    return {"total": total, "limit": limit, "parts": parts}
