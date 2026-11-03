"""文档工具包：agent 成稿入库（网页文档编辑器的数据源）。

只读召回与记忆写入归各域，文档写入是独立的轻产物通道：note-agent 的笔记、
research-agent 的研究计划成稿后经 save_document 落 bio_document 表，用户在网页
「文档编辑器」里查看与继续编辑。
"""
from biopilot.tools.docs.save_document import SaveDocumentTool

__all__ = ["SaveDocumentTool"]
