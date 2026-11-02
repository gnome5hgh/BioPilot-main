"""出站平台边界：调 Java ``/internal/*`` 的薄客户端。"""
from biopilot.common.platform.client import (
    PlatformClient,
    PlatformError,
    make_platform_client,
)

__all__ = ["PlatformClient", "PlatformError", "make_platform_client"]
