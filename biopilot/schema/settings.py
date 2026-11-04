"""设置页 HTTP 契约。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SettingsSnapshotResponse(BaseModel):
    """``GET /settings`` 的响应。"""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    version: int
    values: dict[str, Any]
    sources: dict[str, str]
    settings_schema: list[dict[str, Any]] = Field(alias="schema")
    warning: str


class SettingsPatchRequest(BaseModel):
    """``POST /settings`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    version: Any = None
    reason: str | None = None
    patches: list[dict[str, Any]] | None = None


class SettingsPatchResponse(BaseModel):
    """保存设置的结果。"""

    status: str
    version: int
    applied: list[str]


class SettingsHistoryResponse(BaseModel):
    """``GET /settings/history`` 的响应。"""

    data: list[dict[str, Any]]


class SettingsRollbackRequest(BaseModel):
    """``POST /settings/rollback`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    version: Any = None


class SettingsRollbackResponse(BaseModel):
    """回滚结果。"""

    status: str
    version: int
