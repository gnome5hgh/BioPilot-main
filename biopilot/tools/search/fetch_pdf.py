"""FetchPdfTool：经平台下载 PDF 并登记为分析产物（OSS）。

下载一律经 Java ``/internal/literature/fetch-pdf``（SSRF 逐跳校验与 ``%PDF`` 检查在
Java）；本工具只负责命名、查重与登记产物，不再落本地文件。下载物不自动进论文库。
"""
from __future__ import annotations

from urllib.parse import unquote, urlparse

from biopilot.common.platform import PlatformError
from biopilot.engine.tool import Tool, ToolResult
from biopilot.common.core.utils.text import normalize_title
from biopilot.tools.file._support import current_run_id, current_user_id, platform_for


class FetchPdfTool(Tool):
    """下载 PDF 并登记为平台分析产物的工具。

    Attributes:
        name: str，工具名 "fetch_pdf"
        description: str，工具描述
        parameters: dict，JSON Schema（url/save_as/title）
        risk_level: str，"medium"
        side_effects: list[str]，["network", "write_file"]
        wants_run_state: bool，True（失败 URL 负缓存与成功短路）
    """

    name = "fetch_pdf"
    description = ("下载 PDF 并登记到文件管理（经平台下载，SSRF 与 %PDF 校验在 Java）。"
                   "url 取 search_literature 结果里的 pdf_url；save_as 是保存的文件名"
                   "（默认取 URL 末段）。下载物不自动进入网页论文库。")
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "url",
                    "description": "PDF 下载地址（来自搜索结果的 pdf 字段）"},
            "save_as": {"type": "string", "format": "file_name",
                        "description": "保存的文件名（如 paper.pdf）；缺省取 URL 末段"},
            "title": {"type": "string",
                      "description": "论文标题（来自检索结果），用于查重"},
        },
        "required": ["url"],
    }
    risk_level = "medium"
    side_effects = ["network", "write_file"]
    provenance = None
    wants_run_state = True

    def execute(self, url: str, save_as: str | None = None,
                title: str | None = None, _run_state=None) -> ToolResult:
        """下载 PDF 并上传为分析产物。

        Args:
            url: PDF 地址。
            save_as: 保存文件名；缺省取 URL 末段。
            title: 论文标题（用于查重）。
            _run_state: 本次 run 的状态容器（负缓存与成功短路）。

        Returns:
            ToolResult，文本含 file_id/文件名；失败返回可行动文本。
        """
        if _run_state is not None and url in getattr(_run_state, "failed_urls", {}):
            return ToolResult(
                text=(f"该 URL 本任务内已失败过（{_run_state.failed_urls[url]}），"
                      "这是重复调用——不得重试，请如实报告下载失败并给出替代方案。"),
                is_error=True)
        if _run_state is not None:
            title_key = f"title:{normalize_title(title)}" if title else None
            hit = getattr(_run_state, "downloaded", {}).get(url) or (
                title_key and getattr(_run_state, "downloaded", {}).get(title_key))
            if hit:
                return ToolResult(
                    text=f"本任务内已下载过该论文: {hit}，无需重复下载。")

        name = (save_as or _name_from_url(url) or "paper.pdf").strip()
        user = current_user_id()
        platform = platform_for(self)
        try:
            data = platform.fetch_pdf(user, url)
            if not data.startswith(b"%PDF"):
                return ToolResult(
                    text=f"下载失败: 响应不是 PDF（缺 %PDF magic bytes）: {url}",
                    is_error=True)
            created = platform.upload_artifact(
                user, current_run_id(), name, data, "application/pdf")
        except PlatformError as e:
            status = e.status_code
            if status is not None and 400 <= status < 500:
                reason = f"HTTP {status}（永久性失败，勿重试）"
                if _run_state is not None:
                    _run_state.failed_urls[url] = reason
                return ToolResult(text=f"下载失败: {reason}——{e}", is_error=True)
            return ToolResult(text=f"下载失败: {e}", is_error=True)
        except Exception as e:
            return ToolResult(text=f"下载失败: {e}", is_error=True)
        finally:
            platform.close()

        ref = str(created.get("file_id") or created.get("oss_key") or "")
        if _run_state is not None and ref:
            _run_state.downloaded[url] = ref
            if title:
                _run_state.downloaded[f"title:{normalize_title(title)}"] = ref
        return ToolResult(
            text=(f"已下载 PDF: {created.get('name') or name}"
                  f"（file_id={created.get('file_id')}，oss_key={created.get('oss_key')}）。"
                  "文件已登记到文件管理，尚未进入网页论文库。"))

    def effective_target_key(self, args: dict) -> str | None:
        """确认键作用域：保存文件名。"""
        name = args.get("save_as") or _name_from_url(str(args.get("url") or ""))
        return f"file:{current_user_id()}:{name}" if name else None


def _name_from_url(url: str) -> str:
    """从 URL 末段推一个文件名；推不出返回空串。"""
    path = unquote(urlparse(url or "").path)
    name = path.rsplit("/", 1)[-1].strip()
    return name or ""
