"""SaveDocumentTool：把 markdown 成稿保存进用户的文档编辑器。

文档是平台产物：OSS 对象键、``bio_file`` 元数据与同名覆盖语义都在 Java
``DocumentService`` 里；本工具只做参数校验、内部 HTTP 转发与结果文案。
"""
from __future__ import annotations

from biopilot.common.platform import PlatformError, make_platform_client
from biopilot.engine.tool import Tool, ToolResult
from biopilot.engine.tool.services.runtime_context import get_memory_context
from biopilot.tools.file._support import normalize_name

__all__ = ["SaveDocumentTool"]


def _current_user_id() -> str:
    """取当前 run 的归属用户（转发运行时上下文的统一入口）。"""
    from biopilot.engine.tool.services.runtime_context import current_user_id
    return current_user_id()


class SaveDocumentTool(Tool):
    """按名字把 markdown 全文保存进用户的文档编辑器（同名覆盖、不存在新建）。

    内容与元数据由 Java 平台写入（OSS + ``bio_file``）；本工具只经
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
            "name": {"type": "string", "format": "file_name",
                     "description": "文档名（如 单细胞QC笔记.md）"},
            "content": {"type": "string", "format": "content",
                        "description": "markdown 全文"},
            "expected_version": {"type": "integer",
                                 "description": "可选：乐观锁版本（覆盖已有文档时）"},
        },
        "required": ["name", "content"],
    }
    # 写平台文档（同名覆盖）：写类工具按 high 处理，执行前确认
    risk_level = "high"
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

    def execute(self, name: str, content: str,
                expected_version: int | None = None) -> ToolResult:
        """按 (user_id, name) 保存文档；平台不可用时降级为错误文本。

        Args:
            name: 文档名（空白拒绝；超长与非法路径字符由服务端归一化）。
            content: markdown 全文。
            expected_version: 可选乐观锁版本；409 表示别人先改了。

        Returns:
            ToolResult，文本说明新建/更新结果；平台不可用时给出可行动错误。
        """
        name = (name or "").strip()
        if not name:
            return ToolResult(text="Error: 文档名不能为空", is_error=True)
        platform = self._platform()
        try:
            data = platform.save_document(
                _current_user_id(), name, content or "",
                expected_version=expected_version)
        except PlatformError as e:
            if getattr(e, "status_code", None) == 409:
                return ToolResult(
                    text="文档已被其他会话修改，请先读取最新内容再重试",
                    is_error=True)
            return ToolResult(text=f"文档保存失败：{_brief(str(e))}", is_error=True)
        except Exception as e:
            return ToolResult(text=f"文档保存服务不可用：{e}", is_error=True)
        finally:
            platform.close()
        created = bool(data.get("created"))
        verb = "已保存" if created else "已更新"
        return ToolResult(
            text=(f"{verb}文档《{data.get('name') or name}》"
                  f"（id={data.get('id')}，version={data.get('version')}），"
                  "用户可在网页文档编辑器查看。"))

    def effective_target_key(self, args: dict) -> str | None:
        """确认键作用域：用户 + 归一化文档名。"""
        name = args.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        return f"name:{_current_user_id()}:{normalize_name(name)}"


def _brief(text: str, limit: int = 300) -> str:
    """截断上游错误体，避免把整页 HTML 灌进模型上下文。"""
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[:limit] + "…"
