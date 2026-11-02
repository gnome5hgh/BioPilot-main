# biopilot/core/security/__init__.py
"""
安全中间件协议层与全部具体中间件——包级统一导出。

协议层定义（SecurityMiddleware / 异常体系）在 ``middleware/base.py``，
上下文与审计事件两个契约对象在 ``domain/``：
Python 导入机制规定，当 ``security.py`` 模块与 ``security/`` 包同名共存时，
包总是优先被导入，单独的 ``security.py`` 永远无法以 ``biopilot.core.security``
访问到。把实现放在包内子模块、这里集中导出，可以避免产生无法导入的死代码，
也避免循环导入。具体中间件（审计、工作区路径边界、内容防护与策略检查）在
``middleware/`` 子包；与中间件无关的独立防护能力（命令解析、可选语义判定）在
``services/``；跨模块词汇（决策/审批结果/结果状态词表）在 ``constants/``；未配对
代理字符清洗是跨包共用的叶子，已移入 ``biopilot/common/core/utils/text.py``。
出网防护不在本包：外部 URL 的 SSRF 校验归 Java ``bio-common-net``，配置端点
绑定在 ``biopilot/common/net/``。
"""
from biopilot.core.security.constants import (
    ApprovalOutcome,
    ToolDecision,
    ToolResultStatus,
)
from biopilot.core.security.middleware.base import (
    ConfirmRequired,
    SecurityBlocked,
    SecurityError,
    SecurityMiddleware,
)
from biopilot.core.security.domain import AuditEntry, ToolContext
from biopilot.core.security.middleware.audit import AuditMiddleware
from biopilot.core.security.middleware.workspace import (
    WorkspacePolicy,
    WorkspacePolicyMiddleware,
)
from biopilot.core.security.middleware.content_guard import (
    ContentGuardMiddleware,
    has_critical,
    scan,
)
from biopilot.core.security.middleware.command_guard import CommandGuardMiddleware
from biopilot.core.security.middleware.policy_engine import PolicyEngineMiddleware

__all__ = [
    "ToolContext", "SecurityMiddleware", "SecurityError",
    "ConfirmRequired", "SecurityBlocked",
    "AuditMiddleware", "AuditEntry",
    "WorkspacePolicy", "WorkspacePolicyMiddleware",
    "scan", "has_critical", "ContentGuardMiddleware",
    "CommandGuardMiddleware", "PolicyEngineMiddleware",
    "ApprovalOutcome", "ToolDecision", "ToolResultStatus",
]
