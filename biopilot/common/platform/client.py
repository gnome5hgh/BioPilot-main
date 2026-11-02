"""Java 平台内部端点的薄客户端。

引擎需要平台能力时只走 ``/internal/*``：携带 ``X-User-Id``（归属真相）与可选的
``X-Internal-Token``。本模块是唯一出站实现，避免各工具各写一份 header、超时与
错误映射。失败一律抛 :class:`PlatformError`，由调用方降级为工具文本/日志。
"""
from __future__ import annotations

import os
from urllib.parse import unquote

import httpx

__all__ = ["PlatformClient", "PlatformError", "make_platform_client"]


class PlatformError(RuntimeError):
    """平台内部调用失败（网络异常、非 2xx、响应不可解析）。

    Attributes:
        status_code: HTTP 状态码；网络层失败（连不上/超时）为 None。调用方
            用它区分确定性失败（4xx，不重试）与瞬时故障（5xx/无响应，可重试）。
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PlatformClient:
    """面向 Java 平台内部端点的同步客户端。

    Attributes:
        _base: 平台根地址（已去掉尾部斜杠）。
        _token: 内部调用共享 token；为空时不带该头（与 Java/Python 两侧语义一致）。
        _timeout: 普通请求超时（秒）。
        _transfer_timeout: 文件上传/下载/PDF 抓取等大流量请求的超时（秒）。
        _client: 惰性构造的 httpx.Client。
    """

    def __init__(self, base_url: str, internal_token: str = "", *,
                 timeout: float = 60.0, transfer_timeout: float = 120.0,
                 client: httpx.Client | None = None):
        """绑定平台地址与超时；``client`` 仅供测试注入 MockTransport。

        Args:
            base_url: 平台根地址，例如 ``http://127.0.0.1:8080``。
            internal_token: 内部调用共享 token。
            timeout: 普通请求超时（秒）。
            transfer_timeout: 文件传输类请求超时（秒）。
            client: 可注入的 httpx 客户端（测试用）。
        """
        self._base = (base_url or "").rstrip("/")
        self._token = internal_token or ""
        self._timeout = max(1.0, float(timeout or 60.0))
        self._transfer_timeout = max(1.0, float(transfer_timeout or 120.0))
        self._client = client
        self._own_client = client is None

    def close(self) -> None:
        """关闭自建客户端；注入的客户端由调用方负责。"""
        if self._own_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        """惰性构造并复用 httpx 客户端。"""
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def _headers(self, user_id: str) -> dict:
        """内部调用头：归属用户 + 可选共享 token。"""
        headers = {"X-User-Id": str(user_id)}
        if self._token:
            headers["X-Internal-Token"] = self._token
        return headers

    def _request(self, method: str, path: str, *, user_id: str,
                 timeout: float | None = None, **kwargs) -> httpx.Response:
        """发一次内部请求；网络失败或非 2xx 统一转成 PlatformError。"""
        try:
            response = self._http().request(
                method, f"{self._base}{path}", headers=self._headers(user_id),
                timeout=timeout or self._timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise PlatformError(f"平台服务不可用：{exc}") from exc
        if response.status_code >= 300:
            detail = (response.text or "").strip()[:200]
            raise PlatformError(
                f"平台返回 HTTP {response.status_code}"
                + (f"：{detail}" if detail else ""),
                status_code=response.status_code)
        return response

    def attachment(self, user_id: str, kind: str, obj_id: str) -> tuple[bytes, dict]:
        """取回本人附件的字节与元数据。

        身份只认 ``(kind, id, user_id)``，不信任调用方传来的 oss_key/文件名。

        Args:
            user_id: 归属用户。
            kind: ``file``（数据文件）或 ``paper``（论文原文）。
            obj_id: 对应的业务 id。

        Returns:
            ``(bytes, meta)``；meta 含 name/size/oss_key/content_type。

        Raises:
            PlatformError: 不存在、不属于该用户或平台不可用。
        """
        response = self._request(
            "GET", f"/internal/attachments/{kind}/{obj_id}", user_id=user_id,
            timeout=self._transfer_timeout)
        meta = {
            "name": unquote(response.headers.get("X-File-Name", "") or ""),
            "size": _int_header(response.headers.get("X-File-Size")),
            "oss_key": response.headers.get("X-Oss-Key", "") or "",
            "content_type": (response.headers.get("Content-Type")
                             or "application/octet-stream"),
        }
        return response.content, meta

    def upload_artifact(self, user_id: str, run_id: str, name: str, data: bytes,
                        content_type: str = "application/octet-stream") -> dict:
        """把一个分析产物登记进平台文件表（OSS + ``bio_file_upload``）。

        Args:
            user_id: 归属用户。
            run_id: 本次沙箱运行标识（对象键分段）。
            name: 产物文件名。
            data: 文件字节。
            content_type: MIME 类型。

        Returns:
            平台返回的 ``{file_id, name, size, oss_key, content_type}``。

        Raises:
            PlatformError: 平台不可用或登记失败。
        """
        response = self._request(
            "POST", "/internal/files/artifacts", user_id=user_id,
            data={"run_id": run_id},
            files={"file": (name, data, content_type)},
            timeout=self._transfer_timeout)
        return response.json()

    def fetch_pdf(self, user_id: str, url: str) -> bytes:
        """经平台下载 PDF（复用 Java 的 SSRF 校验与 ``%PDF`` 校验）。

        Args:
            user_id: 归属用户。
            url: PDF 地址。

        Returns:
            PDF 字节。

        Raises:
            PlatformError: 下载失败或平台不可用。
        """
        response = self._request(
            "POST", "/internal/literature/fetch-pdf", user_id=user_id,
            json={"url": url}, timeout=self._transfer_timeout)
        return response.content

    def kb_normalize(self, user_id: str, *, requeue_indexing: bool = False) -> dict:
        """让 Java 把索引状态收敛到勾选状态。

        Args:
            user_id: 归属用户。
            requeue_indexing: 持索引锁时置 true，把遗留的 ``indexing`` 重排。

        Returns:
            ``{reset, queued, requeued}``。
        """
        return self._request(
            "POST", "/internal/kb/normalize", user_id=user_id,
            json={"requeue_indexing": bool(requeue_indexing)}).json()

    def kb_requeue_all(self, user_id: str) -> int:
        """让 Java 把所有已加入知识库的论文重排为 ``queued``（强制重建）。

        状态列只有 Java 能写；引擎的「全部重新索引」只负责触发，不再直接 UPDATE。

        Args:
            user_id: 归属用户。

        Returns:
            int: 实际重排的行数。
        """
        data = self._request(
            "POST", "/internal/kb/requeue-all", user_id=user_id, json={}).json()
        return int(data.get("queued") or 0)

    def kb_indexing(self, user_id: str, paper_ids: list[str]) -> list[str]:
        """把本批论文置为索引中，返回真正被接受的 id。

        Args:
            user_id: 归属用户。
            paper_ids: 待索引论文。

        Returns:
            仍在知识库、被接受的论文 id 列表。
        """
        data = self._request(
            "POST", "/internal/kb/indexing", user_id=user_id,
            json={"paper_ids": [str(p) for p in paper_ids]}).json()
        return [str(item) for item in (data.get("accepted") or [])]

    def kb_result(self, user_id: str, results: list[dict]) -> dict:
        """批量上报索引结果，返回每篇是否真正落盘。

        Args:
            user_id: 归属用户。
            results: 每项 ``{paper_id, ok, chunks, error}``。

        Returns:
            ``{paper_id: bool}``；False 表示索引期间已被移出，调用方应撤回索引产物。
        """
        data = self._request(
            "POST", "/internal/kb/result", user_id=user_id,
            json={"results": results}).json()
        applied = data.get("applied") or {}
        return {str(key): bool(value) for key, value in applied.items()}


def make_platform_client(config) -> PlatformClient:
    """按引擎配置构造平台客户端（``platform`` 段缺失时用本机默认值）。

    Args:
        config: ``BioPilotConfig`` 实例。

    Returns:
        绑定当前部署地址与超时的 PlatformClient。
    """
    platform = getattr(config, "platform", None)
    base_url = (getattr(platform, "base_url", "") or "http://127.0.0.1:8080")
    token = (getattr(platform, "internal_token", "")
             or os.environ.get("BIOPILOT_INTERNAL_TOKEN", "") or "")
    return PlatformClient(
        base_url,
        token,
        timeout=float(getattr(platform, "search_timeout", 60.0) or 60.0),
        transfer_timeout=float(getattr(platform, "transfer_timeout", 120.0) or 120.0),
    )


def _int_header(value: str | None) -> int:
    """把响应头里的整数字符串转成 int；缺失/非法返回 0。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
