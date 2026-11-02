"""FetchPdfTool：从检索结果中的 PDF 链接下载 PDF 到本地资料库（独立下载工具）。

下载职责独立成工具，让搜索工具保持纯只读：写盘副作用集中在本工具，审计日志里
「写盘」动作归于 fetch_pdf，不藏在名为 search 的工具下。

下载一律经 Java `/internal/literature/fetch-pdf`：外部 URL 的 SSRF 逐跳校验与
`%PDF` magic bytes 校验在 Java `bio-common-net` 执行，Python 不再直接抓外部地址
（单机 REPL 需要一个可达的平台后端，与文献检索同一前提）。本工具只负责落盘、
查重与负缓存。
"""
from pathlib import Path
from urllib.parse import urlparse

from biopilot.common.platform.client import PlatformError
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.constants import ScopeRoot
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
        root_hints: list[str]，论文语料根（落点）
        side_effects: list[str]，["network", "write_file"]
        provenance: str | None，None（返回本地路径与状态，无外部内容，不打横幅）
        wants_run_state: bool，True（注入失败 URL 负缓存与已下载短路池）
    """

    name = "fetch_pdf"
    # description 与行为对齐:纯下载,url 取 search_literature 结果里的 PDF 链接(LLM 据此传参)
    description = ("下载 PDF 到本地资料库（经平台下载，SSRF 与 %PDF 校验在 Java 侧；"
                   "入库需另行派发 rag-agent）。url 取 search_literature 结果中的 pdf_url。"
                   "任务文本指定了保存位置时必须用它填 download_to——缺省落 pdf 根只是没指定时的兜底。")
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "url",
                    "description": "PDF 下载地址（来自搜索结果的 pdf 字段）"},
            "download_to": {"type": "string", "format": "path",
                            "description": "PDF 保存绝对路径（缺省落语料库 pdf 根，文件名按 URL 尾段推导）"},
            "title": {"type": "string",
                      "description": "论文标题（来自检索结果），用于语料库查重；缺省仅做文件级查重"},
        },
        "required": ["url"],
    }
    #: 下载是写操作——只读会话(风险上限 low)不应触碰本地资料库
    risk_level = "medium"
    root_hints = [ScopeRoot.PDF]
    side_effects = ["network", "write_file"]
    #: 返回本地路径与状态，无外部内容——不需打 mark 横幅
    provenance = None
    #: 注入 per-run 状态：失败 URL 负缓存（同 URL 本任务内不重复尝试）
    wants_run_state = True

    @staticmethod
    def _default_download_name(url: str) -> str:
        """从 URL 尾段推导保存文件名：取 path 末段（去 query/fragment），
        非 .pdf 结尾（大小写不敏感）补 .pdf；空尾段或 '..' 抛 ValueError。

        Args:
            url: str，PDF 下载地址

        Returns:
            推导出的文件名（非 .pdf 结尾则补 .pdf）；空尾段或 ".." 时抛 ValueError。
        """
        tail = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if not tail or tail == "..":
            raise ValueError(f"无法从 URL 推导文件名: {url}——请显式传 download_to")
        return tail if tail.lower().endswith(".pdf") else f"{tail}.pdf"

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
        """导出写互斥键：本次下载的落盘路径。

        与 execute 的落点推导同源——download_to 优先，否则落到语料库 pdf 根、文件名取
        URL 尾段。推导不出来（没配 pdf 根、或 URL 尾段不能当文件名）时返回 None：那种
        调用本身也会失败，不该占住一个写互斥键。

        Args:
            args: dict，已解析的工具调用参数

        Returns:
            下载落盘的绝对路径；无法推导时 None。
        """
        dest = args.get("download_to")
        if isinstance(dest, str) and dest:
            return dest
        url = args.get("url")
        if not isinstance(url, str) or not url:
            return None
        cfg = getattr(self, "_config", None)
        pdf_root = (getattr(getattr(cfg, "corpus", None), "pdf_dir", "")
                    if cfg is not None else "")
        if not pdf_root:
            return None
        try:
            return str(Path(pdf_root) / self._default_download_name(url))
        except ValueError:
            return None

    def execute(self, url: str, download_to: str | None = None,
                title: str | None = None,
                _run_state=None) -> ToolResult:
        """下载 PDF 到本地；失败返回可行动报错文本。

        查重三道闸（均在写盘之前）：
        1. 本任务内已下载过（URL 或规范化标题命中 downloaded）→ 成功性短路；
        2. 语料库已有该论文（title 传入时查语料标题索引）→ 提示无需下载；
        3. 目标文件已存在 → 跳过下载。
        负缓存（现状语义不变）：同 URL 本任务内 4xx 永久失败即拒绝重试。
        download_to 缺省时落语料库 pdf 根（config.corpus.pdf_dir），文件名按 URL 尾段推导。

        Args:
            url: str，PDF 下载地址
            download_to: str | None，保存绝对路径（缺省落 pdf 根）
            title: str | None，论文标题（用于语料库查重）
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
        if download_to:
            dest = Path(download_to)
        else:
            cfg = getattr(self, "_config", None)
            pdf_root = (getattr(getattr(cfg, "corpus", None), "pdf_dir", "")
                        if cfg is not None else "")
            if not pdf_root:
                return ToolResult(text="下载失败: 未配置语料库 pdf 根且未显式传 download_to——请显式传 download_to 绝对路径", is_error=True)
            try:
                dest = Path(pdf_root) / self._default_download_name(url)
            except ValueError as e:
                return ToolResult(text=f"下载失败: {e}", is_error=True)
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
        # 索引不在这里做：下载成功后由调用方派发 rag-agent 入库
        return ToolResult(text=f"已下载 PDF: {dest}（尚未建立索引，请派发 rag-agent）")
