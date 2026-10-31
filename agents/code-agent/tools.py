"""code-agent 的工具装配：沙箱代码执行 + 只读召回（红线例外装配）。

沙箱与审批正交：run_python 的风险档位与策略引擎判断照常生效，代码在容器内
隔离执行。本角色不装配任何直接写文件工具（分析产物由 run_python 的容器产出）。
"""
from biopilot.tools.code.run_python import RunPythonTool
from biopilot.tools.recall import get_recall_tools

TOOLS = [RunPythonTool()] + get_recall_tools()
