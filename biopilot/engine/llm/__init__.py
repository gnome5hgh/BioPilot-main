# biopilot/engine/llm/__init__.py
"""LLM 域包 —— wire 消息家族、对话客户端与结构化输出。

公共出口（下游一律 `from biopilot.engine.llm import ...`）：
- wire 消息家族 ← domain/dto/messages：基类 ``Message``，按角色分的
  ``SystemMessage`` / ``UserMessage`` / ``AssistantMessage`` / ``ToolMessage``，
  以及从角色字符串还原类型的 ``message_from_role``（持久化回放用）
- ``StructuredOutputConfig``（结构化输出的行为参数）← config
- ``LLMClient`` / ``tool_to_openai_schema`` / ``StructuredOutput`` /
  ``StructuredOutputError`` ← application（编排）与 adapters（协议翻译）

分层：``domain/`` 放消息契约、组件参数与端口（``port.py`` 的 ``ModelClient``），
``application/`` 放结构化抽取编排，``adapters/`` 放 OpenAI 兼容协议翻译（客户端
与 wire 漏斗）——是**服务**而非工具集，故与 `common/`（横向共用的小叶子）分开。

**这里只有 LLM 客户端**：稠密编码与精排的协议与实现在 `biopilot.engine.rag.adapters`
（只服务 RAG）。私有辅助（``_accumulate_stream_chunks`` / ``_extract_json_body`` 等）
也不在此导出，需要时从具体子模块 import。
"""
from biopilot.engine.llm.domain import (
    AssistantMessage,
    Message,
    ResponseMeta,
    SystemMessage,
    ToolMessage,
    Usage,
    UserMessage,
    message_from_role,
    response_meta_from_dict,
    response_meta_to_dict,
)
from biopilot.engine.llm.config import StructuredOutputConfig
from biopilot.engine.llm.adapters.client import LLMClient
from biopilot.engine.llm.adapters.wire import tool_to_openai_schema
from biopilot.engine.llm.application.structured import (
    StructuredOutput,
    StructuredOutputError,
)

__all__ = [
    "LLMClient",
    "Message",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "ResponseMeta",
    "Usage",
    "message_from_role",
    "response_meta_to_dict",
    "response_meta_from_dict",
    "StructuredOutput",
    "StructuredOutputConfig",
    "StructuredOutputError",
    "tool_to_openai_schema",
]
