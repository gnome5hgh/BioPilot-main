"""wire 漏斗：领域消息与 OpenAI 协议格式之间的双向纯函数翻译。

本模块是适配层的**协议翻译**部分——没有 I/O、不持有 SDK 客户端，只有
「领域消息 → OpenAI wire dict」与「Tool 契约 → function calling schema」的
出站翻译。入站方向（协议响应 → 领域对象）由 SDK 客户端内部完成；持久化回放
方向的 ``message_from_role`` 在 ``domain/dto/messages``（那是领域内还原，不是
协议翻译）。

放 adapters 而不是 domain：wire dict 的形状是 OpenAI 协议的语言，不是本系统的
词汇；但它纯函数、零客户端依赖，故 application 层（context_window、记忆落盘）
可以安全消费。
"""
from biopilot.common.utils.text import sanitize_surrogates
from biopilot.engine.llm.domain.dto.messages import (
    AssistantMessage,
    Message,
    ToolMessage,
)




def message_to_openai(m: Message) -> dict:
    """:func:`_message_to_openai` 的公开别名（跨包消费方一律用这个名字）。"""
    return _message_to_openai(m)


def _message_to_openai(m: Message) -> dict:
    """将内部消息转为 OpenAI API 接受的 dict 格式。

    只有非 None 的字段才会出现在输出中 ——
    OpenAI API 拒绝 null tool_call_id 或空 tool_calls 字段。

    角色由消息类型决定（``m.role`` 是子类固定的枚举，取 ``.value`` 出纯字符串）；
    角色特有的字段按类型取：tool_calls 只在 assistant 上、tool_call_id 只在 tool 上。

    Args:
        m: Message，内部消息对象（四个角色子类之一）

    Returns:
        OpenAI wire 格式 dict（None 字段不出现；content 经 surrogate 清洗后随消息角色给出）。
    """
    # 出站边界清洗未配对 surrogate（PDF 提取/工具结果可能携带）——否则 openai
    # SDK UTF-8 编码消息时抛 UnicodeEncodeError: surrogates not allowed，
    # 整轮 ReAct 崩溃（见 common/utils/text.py）。
    content = m.content
    if isinstance(content, list):
        # 视觉 content parts：逐 part 清洗 text 的 surrogate，图片 part 原样透传
        content = [_sanitize_content_part(p) for p in content]
    else:
        content = sanitize_surrogates(content)
    msg: dict = {"role": m.role.value, "content": content}
    if isinstance(m, AssistantMessage) and m.tool_calls is not None:
        msg["tool_calls"] = m.tool_calls
    if isinstance(m, ToolMessage) and m.tool_call_id is not None:
        msg["tool_call_id"] = m.tool_call_id
    return msg


def _sanitize_content_part(part: dict) -> dict:
    """清洗单个 content part 里的文本 surrogate；非 text part 原样返回。

    返回新 dict（不动调用方对象），图片 part 无需清洗直接透传。

    Args:
        part: dict，一个 content part（text / image_url）

    Returns:
        清洗后的新 dict（仅 text part 被改写，图片 part 原样透传）。
    """
    if part.get("type") == "text" and isinstance(part.get("text"), str):
        part = dict(part)
        part["text"] = sanitize_surrogates(part["text"])
    return part


def tool_to_openai_schema(t) -> dict:
    """将 Tool 实例转为 OpenAI function calling JSON Schema。

    Args:
        t: Tool 子类实例

    Returns:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

    这个函数是 Tool 抽象层到 LLM API 的桥接 ——
    Tool 开发者只需定义类的 name/description/parameters 属性，
    Agent 通过此函数自动将工具描述发给 LLM，LLM 据此决定何时以及如何调用工具。
    """
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }
