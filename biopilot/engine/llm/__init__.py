# biopilot/engine/llm/__init__.py
"""LLM 域包 —— wire 消息家族、对话客户端与结构化输出。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：wire 消息家族、
``LLMClient`` / ``StructuredOutput``、``ModelClient`` 端口与协议翻译。
分层：``domain/`` 消息契约与端口、``application/`` 结构化抽取编排、
``adapters/`` OpenAI 兼容协议翻译（客户端与 wire 漏斗）——模块外一律经
``adapters.api`` 或本别名 import。
"""
from biopilot.engine.llm.adapters.api import *  # noqa: F401,F403
from biopilot.engine.llm.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
