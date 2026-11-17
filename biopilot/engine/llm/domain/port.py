"""模型客户端端口（领域层）：编排层消费 LLM 的唯一契约。

对应三层架构方法论的 ``ModelClient`` 接口——应用层（Agent 循环、结构化输出、
视觉看图、query 改写）只依赖本协议，不依赖任何具体客户端类；OpenAI 兼容实现
（``adapters/client.py`` 的 ``LLMClient``）在适配层实现它，测试按结构化类型
传假件即可（无需继承）。

接口面按真实消费收敛：``chat``（完整回复，ReAct/结构化输出/看图）、
``chat_stream``（流式增量 + 回调，仅 ReAct 消费）、``context_window`` 属性
（压缩预算推导读）。其余属性（model/provider/max_tokens/temperature）是实现
细节，未进端口——审计侧经 telemetry_callback 拿元数据，不经属性。
"""
from typing import Protocol

from biopilot.engine.llm.domain.dto.messages import AssistantMessage, Message

__all__ = ["ModelClient"]


class ModelClient(Protocol):
    """对话模型的调用契约：Context 进、AssistantMessage 出。

    Attributes:
        context_window: int | None，模型上下文窗口（token 数）；压缩时推导预算用，
            未知时 None。
    """

    context_window: int | None

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        json_mode: bool = False,
        temperature: float | None = None,
        extra_body: dict | None = None,
        telemetry_callback=None,
    ) -> AssistantMessage:
        """单次非流式调用，返回 assistant 消息（可能带 tool_calls）。

        Args:
            messages: 领域消息列表（四角色子类之一）。
            tools: function calling JSON Schema 列表（None = 不带工具）。
            tool_choice: 工具选择策略。
            json_mode: 是否强制 JSON 输出（结构化抽取用）。
            temperature: 覆盖客户端默认采样温度；None 用默认。
            extra_body: 透传协议扩展字段。
            telemetry_callback: 响应收齐后的元数据回调（不含正文）。

        Returns:
            AssistantMessage：模型回复。
        """
        ...

    async def chat_stream(self, messages, tools=None, tool_choice="auto",
                          on_delta=None, on_reasoning=None,
                          telemetry_callback=None) -> AssistantMessage:
        """流式调用：边收边回调，返回与 chat() 同形状的完整回复。

        Args:
            messages: 领域消息列表。
            tools: function calling JSON Schema 列表。
            tool_choice: 工具选择策略。
            on_delta: 每段 content 片段同步回调（跑在流线程内，只做追加/打印）。
            on_reasoning: 每段思维链片段同步回调；端点不返回时从不触发。
            telemetry_callback: 响应收齐后的元数据回调。

        Returns:
            AssistantMessage：完整回复（含 tool_calls 与响应信封）。
        """
        ...
