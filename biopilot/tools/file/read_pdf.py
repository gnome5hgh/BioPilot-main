"""ReadPdfTool：从平台取回 PDF 字节并在内存中解析为文本。

论文/数据文件都只存在 OSS；通过 ``/internal/attachments`` 取字节后交给
``extract_pdf_bytes``，不再依赖本地路径，也没有目录模糊匹配。
"""
from biopilot.common.platform import PlatformError
from biopilot.core.rag.parsers.pdf_extract import extract_pdf_bytes
from biopilot.core.tool import Tool, ToolResult
from biopilot.tools.file._support import current_user_id, platform_for


class ReadPdfTool(Tool):
    """解析平台 PDF 为 markdown 文本的只读工具。

    Attributes:
        name: str，工具名 "read_pdf"
        description: str，工具描述
        parameters: dict，JSON Schema（id/kind）
        risk_level: str，"low"（只读）
        provenance: str，"pdf"
        side_effects: list[str]，["read_file"]
    """
    name = "read_pdf"
    description = ("解析平台 PDF 为文本（内存提取，章节标题按版面还原）。"
                   "论文用 kind=paper + paper_id；数据文件/产物用 kind=file + file_id。")
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "file_id",
                   "description": "论文/文件 id"},
            "kind": {"type": "string", "enum": ["paper", "file", "data", "artifact"],
                     "description": "paper 或 file/data/artifact；默认 paper"},
        },
        "required": ["id"],
    }
    risk_level = "low"
    provenance = "pdf"
    side_effects = ["read_file"]

    def execute(self, id: str, kind: str = "paper") -> ToolResult:
        """取回 PDF 字节并解析为文本。

        Args:
            id: 论文/文件 id。
            kind: paper/file/data/artifact。

        Returns:
            ToolResult，文本为「标题 + 正文 markdown」；失败时返回可行动错误文本。
        """
        user = current_user_id()
        platform = platform_for(self)
        attachment_kind = "paper" if kind == "paper" else "file"
        try:
            data, meta = platform.attachment(user, attachment_kind, id)
        except PlatformError as e:
            return ToolResult(text=f"读取 PDF 失败：{e}", is_error=True)
        finally:
            platform.close()
        try:
            doc = extract_pdf_bytes(data, title=str(meta.get("name") or ""),
                                    digest=str(meta.get("sha256") or ""))
        except Exception as e:  # PDF 打不开/损坏/加密 → 降级文本
            return ToolResult(text=f"PDF 解析失败：{e}", is_error=True)
        text = doc.body
        if doc.title:
            text = f"# {doc.title}\n\n" + text
        return ToolResult(text=text or "（PDF 未能解析出文本）")
