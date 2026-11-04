"""对话与确认端点的 HTTP 契约。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttachmentRef(BaseModel):
    """消息体里的附件引用；只认 file_id/paper_id，其余字段仅作兼容。"""

    model_config = ConfigDict(extra="ignore")

    file_id: str | None = None
    paper_id: str | None = None
    oss_key: str | None = None
    name: str | None = None
    size: int | None = None


class ChatStreamRequest(BaseModel):
    """``POST /chat/stream`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    task: str = ""
    conversation_id: str = ""
    project_id: str | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    """``POST /chat/confirm`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    req_id: str = ""
    conversation_id: str = ""
    approved: bool = False


class ConfirmResponse(BaseModel):
    """确认回传结果。"""

    status: str = "ok"


class StreamFrame(BaseModel):
    """SSE 帧的形状（仅作文档；流式端点仍直接输出 dict）。"""

    model_config = ConfigDict(extra="allow")

    type: str
    text: str = ""
    agent_type: str = ""
    tool_name: str = ""
    completion: str = ""
    duration_ms: Any = None
