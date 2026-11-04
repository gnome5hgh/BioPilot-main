"""领域异常 → HTTP 响应的统一映射。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from biopilot.config.schema import ConfigValidationError
from biopilot.config.store import (
    ConfigSecretDecryptError,
    ConfigSecretKeyMissing,
    ConfigVersionConflict,
)
from biopilot.service.errors import ServiceError


def register_exception_handlers(app: FastAPI) -> None:
    """注册服务层与配置层异常的响应映射。"""

    @app.exception_handler(ServiceError)
    async def _service_error(_request: Request, exc: ServiceError):
        """把服务层异常映射为统一 JSON 错误。"""
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(ConfigVersionConflict)
    async def _config_conflict(_request: Request, exc: ConfigVersionConflict):
        """把配置乐观锁冲突映射为 409。"""
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ConfigValidationError)
    async def _config_invalid(_request: Request, exc: ConfigValidationError):
        """把配置校验错误映射为 422。"""
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ConfigSecretKeyMissing)
    async def _secret_key_missing(_request: Request,
                                  exc: ConfigSecretKeyMissing):
        """把缺少主密钥映射为 422。"""
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ConfigSecretDecryptError)
    async def _secret_decrypt(_request: Request, exc: ConfigSecretDecryptError):
        """把密钥解密失败映射为 422。"""
        return JSONResponse(status_code=422, content={"detail": str(exc)})
