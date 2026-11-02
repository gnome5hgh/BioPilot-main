"""research-agent 的工具装配：原子文件工具 + 派发 paper-agent/review-agent/rag-agent/citation-agent。

选题发现 agent 自产自写：用 read_pdf 读本地论文 PDF 语料（笔记不进检索知识库、也不参与
溯源，不是本角色的素材），write_file/edit_file
落盘产物（survey/gaps/idea 卡/研究计划）。spawn 工具派发 paper-agent（补料下载、外部
新颖性检索）、review-agent（选题产物审查）、rag-agent（按课题盘点语料——语料检索已收归
它）与 citation-agent（溯源要确认或入库的 key、参考文献渲染——引用库的读写归它，
本角色不装配引用工具）。课题/方向有歧义时把问题写进最终回答（问用户不需要工具）。
"""
from biopilot.config import BioPilotConfig
from biopilot.tools.orchestration.spawn import SpawnSubAgentTool
from biopilot.tools import (
    ReadFileTool, ReadPdfTool, ExtractTitleTool, WriteFileTool, EditFileTool,
    DeleteFileTool, GlobTool, GrepTool,
)
from biopilot.cli.services.tool_assembly import make_tools
from biopilot.tools.docs import SaveDocumentTool
from biopilot.tools.recall import get_recall_tools


TOOLS = make_tools(BioPilotConfig.from_env(), [
    ReadPdfTool, ExtractTitleTool,
    ReadFileTool, WriteFileTool, EditFileTool, DeleteFileTool,
    GlobTool, GrepTool,
    SpawnSubAgentTool(agent_timeouts=BioPilotConfig.from_env().agents.timeouts,
                   max_turns=BioPilotConfig.from_env().agents.max_turns),
    SaveDocumentTool(),  # 四份研究产物成稿后入库（网页文档编辑器可见）
], default_write_root="research") + get_recall_tools()
