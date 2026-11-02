"""SearchLiteratureTool：调 SpringBoot 内部检索端点，保留 agent 的文献检索能力。

检索实现（Europe PMC、MCP 多源、管理员新增的检索源）全部在 Java 平台侧；本工具只做
参数校验、内部 HTTP 转发与结果格式化，不自己去重、不选源、不缓存——一旦在 Python
再写一层检索逻辑，跨栈双轨就会重新出现。

内部端点走 ``/internal/literature/search``，需要 ``X-User-Id`` 与可选的
``X-Internal-Token``（与引擎入站校验共用 ``BIOPILOT_INTERNAL_TOKEN``）。
"""
from __future__ import annotations

import httpx

from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context

__all__ = ["SearchLiteratureTool"]

_DEFAULT_BASE_URL = "http://127.0.0.1:8080"
_DEFAULT_TIMEOUT = 90.0
_ABSTRACT_PREVIEW = 400


def _current_user_id() -> str:
    """取当前 run 的归属用户；未绑定上下文时回退 local（REPL/单机）。"""
    ctx = get_memory_context()
    return getattr(ctx, "user_id", None) or "local"


class SearchLiteratureTool(Tool):
    """检索学术文献的工具：内部转发到 SpringBoot，结果按论文清单回给模型。

    Attributes:
        name: str，工具名 "search_literature"
        description: str，工具描述（何时用、参数、不下载）
        parameters: dict，JSON Schema（query/sources/year_from/year_to/limit）
        risk_level: str，"low"（只读网络检索）
        side_effects: list[str]，["network"]
        provenance: str，"search"（外部内容，走来源标记与内容防护）
        _client: httpx.Client | None，懒建的内部 HTTP 客户端（测试可注入 MockTransport）
    """

    name = "search_literature"
    description = (
        "检索学术文献（多源：Europe PMC、OpenAlex、arXiv 等，由平台配置）。"
        "返回标题、年份、期刊、DOI、开放获取 PDF 链接与 paper id；只检索不下载。"
        "需要全文时把结果里的 pdf_url 交给 fetch_pdf。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索词，建议英文关键词"},
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选，指定检索源（如 europepmc/openalex/arxiv）；不传用平台默认",
            },
            "year_from": {"type": "integer", "description": "起始年份（可选）"},
            "year_to": {"type": "integer", "description": "截止年份（可选）"},
            "limit": {"type": "integer", "description": "返回条数，默认 10，最大 20"},
        },
        "required": ["query"],
    }
    risk_level = "low"
    side_effects = ["network"]
    provenance = "search"

    def __init__(self):
        """初始化工具；HTTP 客户端留待实际调用时懒建。"""
        super().__init__()
        self._client = None

    @classmethod
    def _make_client(cls, transport=None, timeout: float = _DEFAULT_TIMEOUT) -> httpx.Client:
        """构造内部调用客户端；测试经 transport 注入 MockTransport。

        Args:
            transport: httpx.BaseTransport | None，测试注入的假传输
            timeout: float，请求超时秒数

        Returns:
            配置好超时与可选假传输的 httpx.Client。
        """
        return httpx.Client(transport=transport, timeout=timeout)

    def _platform_settings(self) -> tuple[str, str, float]:
        """读取平台地址、内部 token 与超时；未注入配置时用本机默认值。

        Returns:
            (base_url, internal_token, timeout) 三元组。
        """
        cfg = getattr(self, "_config", None)
        platform = getattr(cfg, "platform", None)
        base_url = getattr(platform, "base_url", "") or _DEFAULT_BASE_URL
        token = getattr(platform, "internal_token", "") or ""
        timeout = float(getattr(platform, "search_timeout", _DEFAULT_TIMEOUT)
                        or _DEFAULT_TIMEOUT)
        return base_url.rstrip("/"), token, timeout

    def execute(self, query: str, sources: list[str] | None = None,
                year_from: int | None = None, year_to: int | None = None,
                limit: int = 10) -> ToolResult:
        """检索文献并返回紧凑清单；内部服务失败降级为错误文本。

        Args:
            query: 检索词（空则直接返回错误文本）
            sources: 可选检索源列表；None/空表示平台默认
            year_from: 起始年份（可选）
            year_to: 截止年份（可选）
            limit: 返回条数（夹取到 1-20）

        Returns:
            ToolResult；成功含文献清单，失败含可行动错误文案。
        """
        if not (query or "").strip():
            return ToolResult(text="检索词不能为空。", is_error=True)
        base_url, token, timeout = self._platform_settings()
        payload: dict = {"q": query.strip(), "limit": max(1, min(int(limit or 10), 20))}
        if sources:
            payload["sources"] = [str(s) for s in sources if s]
        if year_from is not None:
            payload["year_from"] = int(year_from)
        if year_to is not None:
            payload["year_to"] = int(year_to)

        headers = {"X-User-Id": _current_user_id()}
        if token:
            headers["X-Internal-Token"] = token

        client = self._client
        own_client = client is None
        if own_client:
            client = self._make_client(timeout=timeout)
        try:
            response = client.post(f"{base_url}/internal/literature/search",
                                   json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return ToolResult(
                text=f"文献检索服务返回错误（HTTP {e.response.status_code}）："
                     f"{_brief(e.response.text)}",
                is_error=True)
        except Exception as e:
            return ToolResult(text=f"文献检索服务不可用：{e}", is_error=True)
        finally:
            if own_client:
                client.close()

        results = data.get("results") or []
        errors = data.get("errors") or {}
        text = self._format_results(query, results, errors)
        return ToolResult(
            text=text,
            summary={"count": len(results), "sources": list((data.get("sources") or {}).keys())},
            completion=f"检索到 {len(results)} 篇文献",
        )

    @staticmethod
    def _format_results(query: str, results: list[dict], errors: dict) -> str:
        """把平台返回的候选清单渲染成模型易读的紧凑文本。

        Args:
            query: 原始检索词
            results: 平台返回的候选条目
            errors: 源名 → 失败原因

        Returns:
            文献清单文本；无结果或部分源失败时附明确说明。
        """
        lines: list[str] = []
        if results:
            lines.append(f"检索「{query}」找到 {len(results)} 篇文献：")
        else:
            lines.append(f"检索「{query}」未找到相关文献。")
        for index, item in enumerate(results, start=1):
            title = (item.get("title") or "（无标题）").strip()
            year = item.get("pubdate") or "年份未知"
            journal = item.get("journal") or "期刊未知"
            source = item.get("source") or "未知来源"
            lines.append(f"{index}. {title} | {year} | {journal} | 来源：{source}")
            identifiers = []
            if item.get("id"):
                identifiers.append(f"id={item['id']}")
            if item.get("doi"):
                identifiers.append(f"DOI={item['doi']}")
            if item.get("pmid"):
                identifiers.append(f"PMID={item['pmid']}")
            if identifiers:
                lines.append("   " + "；".join(identifiers))
            pdf_url = item.get("pdf_url") or ""
            lines.append("   " + (f"PDF：{pdf_url}" if pdf_url else "PDF：无开放获取全文"))
            abstract = (item.get("abstract") or "").strip()
            if abstract:
                if len(abstract) > _ABSTRACT_PREVIEW:
                    abstract = abstract[:_ABSTRACT_PREVIEW].rstrip() + "…"
                lines.append(f"   摘要：{abstract}")
        if errors:
            detail = "；".join(f"{name}: {reason}" for name, reason in errors.items())
            lines.append(f"部分检索源失败：{detail}")
        if results:
            lines.append("需要全文时把 PDF 链接交给 fetch_pdf；不要编造未返回的文献。")
        return "\n".join(lines)


def _brief(text: str, limit: int = 300) -> str:
    """截断上游错误体，避免把整页 HTML 灌进模型上下文。"""
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[:limit] + "…"
