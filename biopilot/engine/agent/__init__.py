# biopilot/engine/agent/__init__.py
"""Agent 域包 —— ReAct 运行时、注册表与行为基座。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：``Agent`` /
``AgentRegistry`` / 运行期状态容器 / 事件契约 / 上下文用量 / ``build_agent``。
依赖方向：本包可依赖 engine.llm / engine.skills / engine.tools / engine.memory /
engine.security / engine.intent / biopilot.common（全部经对方 adapters）；
反向（它们 import 本包）不被允许。
"""
from biopilot.engine.agent.adapters.api import *  # noqa: F401,F403
from biopilot.engine.agent.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
