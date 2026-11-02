"""paper-agent 的工具装配：论文域的全部工具面——检索、下载/删除、文件定位、读 PDF 与图表。

检索走 SearchLiteratureTool：它只把参数转发给 SpringBoot 的内部检索端点，Europe PMC、
MCP 多源与管理员新增检索源都在 Java 侧实现。下载用 FetchPdfTool（落到工作区供本轮
阅读）、定位用 glob/grep、读整篇用 read_pdf、图表用 analyze_figures；SpawnSubAgentTool
用于派发 rag-agent（入库与收敛索引）。spawn 工具需要构造
参数 (agent_timeouts)，故 make_tools 传已实例化的工具实例而非类。

需要用户拿主意时把问题写进最终回答（问用户不需要工具），不自行猜。
"""
from biopilot.config import BioPilotConfig
from biopilot.cli.services.tool_assembly import make_tools
from biopilot.tools.orchestration.spawn import SpawnSubAgentTool
from biopilot.tools import (
    FetchPdfTool, DeleteFileTool, GlobTool, GrepTool, ReadPdfTool,
    SearchLiteratureTool,
)
from biopilot.tools.vision.analyze_figures import AnalyzeFiguresTool
from biopilot.tools.recall import get_recall_tools

TOOLS = make_tools(BioPilotConfig.from_env(), [
    SearchLiteratureTool(),
    FetchPdfTool, DeleteFileTool, GlobTool, GrepTool,
    ReadPdfTool,
    AnalyzeFiguresTool(),
]) + [SpawnSubAgentTool(agent_timeouts=BioPilotConfig.from_env().agents.timeouts,
                   max_turns=BioPilotConfig.from_env().agents.max_turns)] + get_recall_tools()
