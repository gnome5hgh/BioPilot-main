"""文件工具共用的平台调用小工具。"""
from __future__ import annotations

import mimetypes
import unicodedata

from biopilot.common.platform import make_platform_client
from biopilot.core.tool.services.runtime_context import get_memory_context


def current_user_id() -> str:
    """取当前 run 的归属用户；未绑定上下文时回退 ``local``（REPL/单机）。"""
    ctx = get_memory_context()
    return str(getattr(ctx, "user_id", None) or "local")


def current_run_id() -> str:
    """取当前 run 的标识；没有时回退 ``run``。"""
    ctx = get_memory_context()
    return str(getattr(ctx, "agent_id", None) or "run")


def platform_for(tool):
    """按工具的配置快照构造平台客户端；未注入配置时回退环境配置。"""
    cfg = getattr(tool, "_config", None)
    if cfg is None:
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
    return make_platform_client(cfg)


def content_type_for(name: str) -> str:
    """按文件名推断 MIME；未知类型回退二进制。"""
    guessed, _ = mimetypes.guess_type(name or "")
    return guessed or "application/octet-stream"


def normalize_name(name: str) -> str:
    """与 Java ``name_key`` 同口径：NFC + trim + lower。"""
    return unicodedata.normalize("NFC", (name or "").strip()).lower()
