"""模型清单与选择 HTTP 契约。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelItem(BaseModel):
    """一个可选模型条目。"""

    name: str
    model: str
    current: bool


class ModelsResponse(BaseModel):
    """``GET /models`` 的响应。"""

    models: list[ModelItem]
    selected: str | None = None
    base_model: str


class ModelSelectRequest(BaseModel):
    """``POST /models/select`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""


class ModelSelectResponse(BaseModel):
    """模型选择结果。"""

    status: str
    selected: str | None = None
