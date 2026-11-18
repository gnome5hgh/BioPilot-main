"""llm 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

本模块是 ``biopilot.engine.llm`` 对外的唯一声明处：模块外的调用方（FastAPI 侧、
其它 engine 模块）一律 ``from biopilot.engine.llm.adapters.api import ...`` 或经
包根别名（``from biopilot.engine.llm import ...``，根只做本文件的再导出）。
出向实现（OpenAI 兼容协议翻译）同住 ``adapters/``，同属公开面。
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
from biopilot.engine.llm.domain.port import ModelClient
from biopilot.engine.llm.config import StructuredOutputConfig
from biopilot.engine.llm.adapters.client import LLMClient
from biopilot.engine.llm.adapters.wire import message_to_openai, tool_to_openai_schema
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
    "ModelClient",
    "StructuredOutput",
    "StructuredOutputConfig",
    "StructuredOutputError",
    "tool_to_openai_schema",
    "message_to_openai",
    "build_llm",
]


def build_llm(config):
    """按全局配置构造主对话模型客户端（模块对外唯一的组装入口）。

    Args:
        config: BioPilotConfig（取 ``llm`` 段）。

    Returns:
        LLMClient：实现 ``ModelClient`` 端口的对话模型客户端。
    """
    return LLMClient(config.llm)
