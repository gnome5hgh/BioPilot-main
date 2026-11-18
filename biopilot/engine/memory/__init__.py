"""biopilot 核心记忆子系统。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：领域模型、服务层
（块/消息/agent 管理器）、压缩配置、MemoryConsolidator 后台整合、MySQL 存储
与命名锁、会话级轻量查询。分层依赖单向：domain（schemas/entity/dto/errors/ports）
→ application（编排）→ adapters（MySQL 持久化与命名锁 + 公开契约）；
模块外一律经 ``adapters.api`` 或本别名 import。
"""
from biopilot.engine.memory.adapters.api import *  # noqa: F401,F403
from biopilot.engine.memory.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
