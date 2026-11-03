"""paper-agent 的工具装配：论文域的全部工具面——检索、下载/删除、文件定位、读 PDF 与图表。

检索走 SearchLiteratureTool：它只把参数转发给 SpringBoot 的内部检索端点，Europe PMC、
MCP 多源与管理员新增检索源都在 Java 侧实现。下载用 FetchPdfTool（落到工作区供本轮
阅读）、定位用 glob/grep、读整篇用 read_pdf、图表用 analyze_figures。
本角色是叶子角色（allowed_spawns: []），不装 spawn 工具。

需要用户拿主意时把问题写进最终回答（问用户不需要工具），不自行猜。
"""
from biopilot.config import BioPilotConfig
from biopilot.cli.services.tool_assembly import make_tools
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
]) + get_recall_tools()
# 叶子角色（allowed_spawns: []）：不装 spawn 工具——装了也只会在框架层被拒绝，
# 白占 schema 并向模型广告一个不存在的能力。
