"""知识库运行时 HTTP 契约。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class KbReindexRequest(BaseModel):
    """``POST /kb/reindex`` 的可选请求体。"""

    model_config = ConfigDict(extra="ignore")


class KbReindexResponse(BaseModel):
    """重建触发结果。"""

    status: str
    already_running: bool


class KbSearchRequest(BaseModel):
    """``POST /kb/search`` 的请求体。"""

    model_config = ConfigDict(extra="ignore")

    query: str = ""
    top_k: Any = 8


class KbChunkView(BaseModel):
    """一个检索/分块结果的展示视图。"""

    id: Any
    text: str
    path: Any
    title: Any
    heading: Any
    caption: Any
    chunk_type: Any
    chunk_index: Any
    page: list[Any]
    has_image: bool
    score: float | None = None


class KbSearchResult(KbChunkView):
    """检索结果额外带平台论文 id。"""

    paper_id: str


class KbSearchResponse(BaseModel):
    """``POST /kb/search`` 的响应。"""

    results: list[KbSearchResult]
    elapsed_ms: int
    query: str


class KbChunksResponse(BaseModel):
    """``GET /kb/papers/{paper_id}/chunks`` 的响应。"""

    chunks: list[KbChunkView]
