"""兼容旧导入路径：会话装配实现已迁到 ``service/impl/assembly_service_impl.py``。"""
from __future__ import annotations

from biopilot.domain.web_session import WebSession
from biopilot.service.impl.assembly_service_impl import (
    AuditMiddleware,
    IntentService,
    JevClient,
    LLMClient,
    _approved_tools,
    _shared_platform_client,
    assemble_web_session,
    sync_user_skills,
)

__all__ = [
    "WebSession", "assemble_web_session", "_approved_tools",
    "_shared_platform_client", "LLMClient", "AuditMiddleware", "JevClient",
    "IntentService", "sync_user_skills",
]
