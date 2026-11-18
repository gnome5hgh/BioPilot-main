"""security 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块）一律经本文件或包根别名使用 security：
中间件洋葱（四件）、协议与异常体系、上下文/审计契约对象、外部语义判定客户端、
审计落库。出向实现（外部判定服务、Docker 沙箱、MySQL 审计）同住 ``adapters/``，
同属公开面。
"""
from biopilot.engine.security.adapters.audit_store import MySqlAuditSink
from biopilot.engine.security.adapters.classifier import build_classifier
from biopilot.engine.security.application.command import analyze, parse  # noqa: F401
from biopilot.engine.security.application.middleware.audit import AuditMiddleware
from biopilot.engine.security.application.middleware.base import (
    ConfirmRequired,
    SecurityBlocked,
    SecurityError,
    SecurityMiddleware,
)
from biopilot.engine.security.application.middleware.command_guard import CommandGuardMiddleware
from biopilot.engine.security.application.middleware.content_guard import (
    ContentGuardMiddleware,
    has_critical,
    scan,
)
from biopilot.engine.security.application.middleware.policy_engine import PolicyEngineMiddleware
from biopilot.engine.security.constants import ApprovalOutcome, ToolDecision, ToolResultStatus
from biopilot.engine.security.domain import AuditEntry, ToolContext
from biopilot.engine.security.domain.ports import AuditSink

__all__ = [
    "ToolContext", "SecurityMiddleware", "SecurityError",
    "ConfirmRequired", "SecurityBlocked",
    "AuditMiddleware", "AuditEntry",
    "scan", "has_critical", "ContentGuardMiddleware",
    "CommandGuardMiddleware", "PolicyEngineMiddleware",
    "ApprovalOutcome", "ToolDecision", "ToolResultStatus",
    "AuditSink", "MySqlAuditSink", "build_classifier", "parse", "analyze",
    "build_middlewares",
]


def build_middlewares(config, db, confirm_above: str | None = None):
    """装配一次会话的安全中间件洋葱（模块对外唯一的组装入口）。

    顺序即执行顺序（before 顺序 / after 逆序）：审计 → 内容防护 → 命令防护 →
    策略引擎。判定客户端由配置构造（未配 key 时为 None，内容防护退纯规则）。

    Args:
        config: BioPilotConfig（取 ``security.pre_approved_tools`` 与判定段）。
        db: MemoryDB，审计落库句柄。
        confirm_above: 确认档位；None 时按 config.security 现值。

    Returns:
        list[SecurityMiddleware]。
    """
    return [
        AuditMiddleware(MySqlAuditSink(db)),
        ContentGuardMiddleware(classifier=build_classifier(config)),
        CommandGuardMiddleware(),
        PolicyEngineMiddleware(
            confirm_above=(confirm_above if confirm_above is not None
                           else config.runtime.confirm_above)),
    ]
