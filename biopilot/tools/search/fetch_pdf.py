"""FetchPdfTool：从检索结果中的 PDF 链接下载 PDF 到指定路径（独立下载工具）。

下载职责独立成工具，让搜索工具保持纯只读：写盘副作用集中在本工具，审计事件里
「写盘」动作归于 fetch_pdf，不藏在名为 search 的工具下。

下载一律经 Java `/internal/literature/fetch-pdf`：外部 URL 的 SSRF 逐跳校验与
`%PDF` magic bytes 校验在 Java `bio-common-net` 执行，Python 不再直接抓外部地址
（单机 REPL 需要一个可达的平台后端，与文献检索同一前提）。本工具只负责落盘、
查重与负缓存。**没有默认 PDF 语料根**：download_to 必填，落点由任务文本给出。
"""
from pathlib import Path

from biopilot.common.platform.client import PlatformError
from biopilot.core.tool import Tool, ToolResult
from biopilot.common.storage.atomic import atomic_write_bytes
from biopilot.common.core.utils.text import normalize_title


def _current_user_id() -> str:
    """取当前 run 的归属用户；未绑定上下文时回退 ``local``（REPL/单机）。"""
    from biopilot.core.tool.services.runtime_context import get_memory_context
    ctx = get_memory_context()
    return str(getattr(ctx, "user_id", None) or "local") if ctx is not None else "local"


class FetchPdfTool(Tool):
    """下载 PDF 工具：经平台下载（SSRF 校验在 Java）+ 写盘。

    Attributes:
        name: str，工具名 "fetch_pdf"
        description: str，工具描述
        parameters: dict，JSON Schema（url/download_to/title）
        risk_level: str，"medium"（写操作，只读会话不应触碰本地资料库）
        side_effects: list[str]，["network", "write_file"]
        provenance: str | None，None（返回本地路径与状态，无外部内容，不打横幅）
        wants_run_state: bool，True（注入失败 URL 负缓存与已下载短路池）
    """

    name = "fetch_pdf"
    # description 与行为对齐:纯下载,url 取 search_literature 结果里的 PDF 链接(LLM 据此传参)
    description = ("下载 PDF 到指定路径（经平台下载，SSRF 与 %PDF 校验在 Java 侧）。"
                   "url 取 search_literature 结果中的 pdf_url；download_to 必填，"
                   "由任务文本给出的绝对路径决定落点。下载物只在工作区，不入平台论文库。")
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "url",
                    "description": "PDF 下载地址（来自搜索结果的 pdf 字段）"},
            "download_to": {"type": "string", "format": "path",
                            "description": "PDF 保存绝对路径（必填）"},
            "title": {"type": "string",
                      "description": "论文标题（来自检索结果），用于文件级查重"},
        },
        "required": ["url", "download_to"],
    }
    #: 下载是写操作——只读会话(风险上限 low)不应触碰本地资料库
    risk_level = "medium"
    side_effects = ["network", "write_file"]
    #: 返回本地路径与状态，无外部内容——不需打 mark 横幅
    provenance = None
    #: 注入 per-run 状态：失败 URL 负缓存（同 URL 本任务内不重复尝试）
    wants_run_state = True

    def _fetch(self, url: str, dest: Path) -> None:
        """经平台下载 PDF 字节并落盘。

        Args:
            url: str，下载地址
            dest: Path，落盘目标

        Raises:
            PlatformError: 平台不可用或下载失败（状态码见 ``status_code``）；
                响应缺 ``%PDF`` magic bytes 按 422（确定性失败）抛出。
        """
        from biopilot.common.platform import make_platform_client
        from biopilot.config import BioPilotConfig
        platform = make_platform_client(BioPilotConfig.from_env())
        try:
            data = platform.fetch_pdf(_current_user_id(), url)
        finally:
            platform.close()
        if not data.startswith(b"%PDF"):
            # 平台侧已做 %PDF 校验，这里是写盘前最后一道兜底；按确定性失败处理
            raise PlatformError(f"响应不是 PDF（缺 %PDF magic bytes）: {url}", status_code=422)
        atomic_write_bytes(dest, data)

    def effective_target_path(self, args: dict) -> str | None:
        """导出写互斥键：本次下载的落盘路径（download_to，必填）。

        Args:
            args: dict，已解析的工具调用参数

        Returns:
            下载落盘的绝对路径；未给 download_to 时 None。
        """
        dest = args.get("download_to")
        return dest if isinstance(dest, str) and dest else None

    def execute(self, url: str, download_to: str | None = None,
                title: str | None = None,
                _run_state=None) -> ToolResult:
        """下载 PDF 到显式路径；失败返回可行动报错文本。

        查重前提（均在写盘之前）：
        1. 本任务内已按 URL 或规范化标题下载过 → 成功性短路；
        2. 目标文件已存在 → 跳过下载。
        负缓存（现状语义不变）：同 URL 本任务内 4xx 永久失败即拒绝重试。
        download_to 必填，没有默认 PDF 落盘根。

        Args:
            url: str，PDF 下载地址
            download_to: str | None，保存绝对路径（必填，没有默认落盘根）
            title: str | None，论文标题（用于文件级查重）
            _run_state: RunState | None，本次 run 的状态容器（负缓存与成功短路）

        Returns:
            ToolResult，文本含落盘路径与状态；失败返回可行动报错文本。
        """
        if _run_state is not None and url in getattr(_run_state, "failed_urls", {}):
            return ToolResult(
                text=f"该 URL 本任务内已失败过（{_run_state.failed_urls[url]}），"
                     "这是重复调用——不得重试，请如实报告下载失败并给出替代方案。",
                is_error=True)
        if _run_state is not None:
            title_key = f"title:{normalize_title(title)}" if title else None
            hit = getattr(_run_state, "downloaded", {}).get(url) or (
                title_key and getattr(_run_state, "downloaded", {}).get(title_key))
            if hit:
                return ToolResult(
                    text=f"本任务内已下载过该论文: {hit}，无需重复下载。")
        if not download_to:
            return ToolResult(
                text="下载失败: 必须显式传 download_to 绝对路径（没有默认 PDF 语料根）",
                is_error=True)
        dest = Path(download_to)
        if dest.exists():
            return ToolResult(text=f"已存在，跳过下载: {dest}")
        try:
            self._fetch(url, dest)
        except PlatformError as e:
            status = e.status_code
            if status is not None and 400 <= status < 500:
                # 4xx 属确定性失败（URL 不存在/无权限/地址或内容不合法）：记入负缓存并明示「勿重试」
                reason = f"HTTP {status}（永久性失败，勿重试）"
                if _run_state is not None:
                    _run_state.failed_urls[url] = reason
                return ToolResult(text=f"下载失败: {reason}——{e}", is_error=True)
            # 5xx/网络不可达是瞬时故障，交通用失败路径（允许重试）
            return ToolResult(text=f"下载失败: {e}", is_error=True)
        except Exception as e:
            # 写盘类异常（权限、路径问题等）：不记负缓存，允许重试
            return ToolResult(text=f"下载失败: {e}", is_error=True)
        if _run_state is not None:
            _run_state.downloaded[url] = str(dest)
            if title:
                _run_state.downloaded[f"title:{normalize_title(title)}"] = str(dest)
            # 写盘已成功（_fetch 内完成），登记产物路径 -> 生产者
            _run_state.artifacts[str(dest)] = "fetch_pdf"
        # 下载物只是工作区文件：平台论文库的登记/入库由用户在网页操作
        return ToolResult(text=f"已下载 PDF: {dest}（工作区文件，尚未进入网页论文库）")
