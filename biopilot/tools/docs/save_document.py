"""SaveDocumentTool：把 markdown 成稿保存进用户的文档编辑器（转发到 Java 平台）。

文档是平台产物：OSS 对象键、`bio_document` 元数据与同名覆盖语义都在 Java
`DocumentService` 里，本工具只做参数校验、内部 HTTP 转发与结果文案，不再直接读写
平台表或对象存储。
"""
from __future__ import annotations

from biopilot.common.platform import PlatformError, make_platform_client
from biopilot.core.tool import Tool, ToolResult
from biopilot.core.tool.services.runtime_context import get_memory_context

__all__ = ["SaveDocumentTool"]


def _current_user_id() -> str:
    """取当前 run 的归属用户；未绑定上下文时回退 local（REPL/单机）。"""
    ctx = get_memory_context()
    return getattr(ctx, "user_id", None) or "local"


class SaveDocumentTool(Tool):
    """按名字把 markdown 全文保存进用户的文档编辑器（同名覆盖、不存在新建）。

    内容与元数据由 Java 平台写入（OSS + `bio_document`）；本工具只经
    ``/internal/documents/save`` 转发，不碰文件系统、不进检索库。
    """

    name = "save_document"
    description = (
        "把 markdown 文档保存到用户的文档编辑器（按名字保存：同名覆盖、不存在新建）。"
        "笔记、研究计划等成稿在定稿后调用本工具入库，用户即可在网页文档编辑器中查看。"
        "name 是文档名（建议以 .md 结尾），content 是 markdown 全文。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "文档名（如 单细胞QC笔记.md）"},
            "content": {"type": "string", "description": "markdown 全文"},
        },
        "required": ["name", "content"],
    }
    # 写平台文档（同名覆盖）：写类工具一律至少 medium，默认确认档下会弹一次确认，
    # 避免静默覆盖用户已有文档
    risk_level = "medium"
    side_effects = ["network", "write_file"]

    def __init__(self):
        """初始化工具；平台客户端留待实际调用时构造。"""
        super().__init__()
        #: 测试注入点：注入 httpx.Client 时复用同一个假传输
        self._client = None

    def _platform(self):
        """按本 run 的配置快照构造平台客户端；未注入配置时回退环境配置。"""
        cfg = getattr(self, "_config", None)
        if cfg is None:
            from biopilot.config import BioPilotConfig
            cfg = BioPilotConfig.from_env()
        return make_platform_client(cfg, client=self._client)

    def execute(self, name: str, content: str) -> ToolResult:
        """按 (user_id, name) 保存文档；平台不可用时降级为错误文本。

        Args:
            name: 文档名（空白拒绝；超长与非法路径字符由服务端归一化）。
            content: markdown 全文。

        Returns:
            ToolResult，文本说明新建/更新结果；平台不可用时给出可行动错误。
        """
        name = (name or "").strip()
        if not name:
            return ToolResult(text="Error: 文档名不能为空", is_error=True)
        platform = self._platform()
        try:
            data = platform.save_document(_current_user_id(), name, content or "")
        except PlatformError as e:
            return ToolResult(text=f"文档保存失败：{_brief(str(e))}", is_error=True)
        except Exception as e:
            return ToolResult(text=f"文档保存服务不可用：{e}", is_error=True)
        finally:
            platform.close()
        created = bool(data.get("created"))
        verb = "已保存" if created else "已更新"
        return ToolResult(
            text=f"{verb}文档《{data.get('name') or name}》，用户可在网页文档编辑器查看。")


def _brief(text: str, limit: int = 300) -> str:
    """截断上游错误体，避免把整页 HTML 灌进模型上下文。"""
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[:limit] + "…"
