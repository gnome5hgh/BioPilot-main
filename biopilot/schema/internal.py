"""Java ↔ Python 内部调用 HTTP 契约。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class KbSyncRequest(BaseModel):
    """``POST /internal/kb/sync`` 的可选请求体。"""

    model_config = ConfigDict(extra="ignore")


class KbSyncResponse(BaseModel):
    """索引唤醒结果。"""

    status: str


class KbRuntimeResponse(BaseModel):
    """``GET /internal/kb/runtime`` 的响应。"""

    collection: str
    embedding_model: str
    running: bool
    last_run: dict[str, Any] | None = None


class ScheduleRunRequest(BaseModel):
    """``POST /internal/schedule/run`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    task_id: str = ""
    conversation_id: str = ""
    task: str = ""
    name: str = ""


class ScheduleRunResponse(BaseModel):
    """定时任务投递结果。"""

    status: str


class MarkDeletingResponse(BaseModel):
    """删户第一阶段结果。"""

    status: str


class PurgeResponse(BaseModel):
    """删户物理清理结果。"""

    status: str
    user_id: str
