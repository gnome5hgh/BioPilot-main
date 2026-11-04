"""服务层领域异常。

controller 不再到处手写 HTTP 状态码；``api/exception_handlers.py`` 把这些异常
统一映射为 ``{"detail": ...}``，状态码与文案与旧实现逐条一致。
"""
from __future__ import annotations


class ServiceError(Exception):
    """带 HTTP 状态码语义的领域异常基类。"""

    status_code = 500

    def __init__(self, detail: str, status_code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class RequestValidationError(ServiceError):
    """请求语义不合法（对应旧实现的 422）。"""

    status_code = 422


class ForbiddenError(ServiceError):
    """权限/信任边界拒绝（对应旧实现的 403）。"""

    status_code = 403


class NotFoundError(ServiceError):
    """资源不存在（对应旧实现的 404）。"""

    status_code = 404


class ConflictError(ServiceError):
    """资源冲突/占用（对应旧实现的 409）。"""

    status_code = 409


class TooManyRequestsError(ServiceError):
    """并发配额超限（对应旧实现的 429）。"""

    status_code = 429


class ServiceUnavailableError(ServiceError):
    """依赖不可用（对应旧实现的 503）。"""

    status_code = 503


class KbBusyError(ConflictError):
    """知识库正被索引占用，只读请求快速失败。"""


class ConfigSourceUnavailable(ServiceUnavailableError):
    """当前进程没有启用数据库配置源。"""
