"""带 SSRF 防护的 PDF 下载核心。

工具（`tools/search/fetch_pdf.py`）与平台导入端点共用这一份实现：逐跳校验
重定向目标、拒绝非公网地址、校验 `%PDF` magic bytes。这样「LLM 下载工具」与
「平台文献导入」不会各写一套安全逻辑。
"""
from __future__ import annotations

from urllib.parse import urljoin

import httpx

from biopilot.core.security.services.network import validate_url_target

__all__ = ["fetch_pdf_bytes"]


def fetch_pdf_bytes(url: str, *, client: httpx.Client | None = None,
                    ssrf_check=None) -> bytes:
    """下载 PDF 字节；每一跳重定向都做 SSRF 校验，响应必须是 `%PDF`。

    Args:
        url: 下载地址。
        client: 可注入的 httpx 客户端（测试用 MockTransport）；None 时新建。
        ssrf_check: URL 校验回调；None 时用 ``validate_url_target``。

    Returns:
        PDF 的完整字节内容。

    Raises:
        RuntimeError: 重定向缺 Location 或超过 5 跳。
        ValueError: 响应不是 PDF（缺 `%PDF` magic bytes）。
        httpx.HTTPStatusError: 上游 4xx/5xx。
        SSRFError: 目标地址落在私网/回环/元数据端点。
    """
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    check = ssrf_check or validate_url_target
    try:
        check(url)
        current = url
        for _ in range(5):
            response = http.get(current, follow_redirects=False)
            if not response.is_redirect:
                break
            location = response.headers.get("location", "")
            if not location:
                raise RuntimeError(f"重定向缺 Location 头: {current}")
            current = urljoin(current, location)
            check(current)
        else:
            raise RuntimeError(f"重定向超过 5 跳: {url}")
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise ValueError(f"响应不是 PDF（缺 %PDF magic bytes）: {url}")
        return response.content
    finally:
        if own_client:
            http.close()
