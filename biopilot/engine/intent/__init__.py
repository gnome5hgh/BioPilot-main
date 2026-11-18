"""意图识别（可选预处理层）。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：意图识别服务、
随包知识库装载、判定客户端。知识库随包放在 ``domain/data/``，由 adapters 的
``load_taxonomy`` 装载并做 fail-closed 校验；判定服务不可达则整层不装配。
模块外一律经 ``adapters.api`` 或本别名 import。
"""
from biopilot.engine.intent.adapters.api import *  # noqa: F401,F403
from biopilot.engine.intent.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
