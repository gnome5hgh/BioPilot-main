"""bio-agent 的工具装配：沙箱执行 + 数据读取 + 成稿入库。

本角色是沙箱执行能力的唯一持有者：run_python 负责在隔离容器里跑代码（镜像预装库
以工具描述为准）；read_file/glob/grep 负责找到并读取任务给定的数据文件；
save_document 把分析报告入库文档编辑器。不装 spawn（本角色无子任务）、不装写文件
工具（分析产物经沙箱 scratch 带回宿主路径，报告走 save_document）。
"""
from biopilot.config import BioPilotConfig
from biopilot.tools import (
    GlobTool, GrepTool, ReadFileTool, ReadPdfTool,
)
from biopilot.tools.code.run_python import RunPythonTool
from biopilot.tools.docs import SaveDocumentTool
from biopilot.tools.recall import get_recall_tools

# run_python 的沙箱政策来自装配配置；本角色不走 make_tools（无写文件工具可注入），
# 配置就地直注——缺了它 execute 恒返回「未装配配置」，沙箱链路整体空转。
_run_python = RunPythonTool()
_run_python._config = BioPilotConfig.from_env()

TOOLS = [
    ReadFileTool, GlobTool, GrepTool, ReadPdfTool,
    _run_python,
    SaveDocumentTool(),
] + get_recall_tools()
