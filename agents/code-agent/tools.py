"""code-agent 的工具装配：沙箱代码执行 + 只读召回（红线例外装配）。

沙箱与审批正交：run_python 的风险档位与策略引擎判断照常生效，代码在容器内
隔离执行。本角色不装配任何直接写文件工具（分析产物由 run_python 的容器产出）。
"""
from biopilot.config import BioPilotConfig
from biopilot.tools.code.run_python import RunPythonTool
from biopilot.tools.recall import get_recall_tools

# run_python 的沙箱政策来自装配配置；本角色不走 make_tools（无写文件工具可注入），
# 配置就地直注——缺了它 execute 恒返回「未装配配置」，沙箱链路整体空转。
_run_python = RunPythonTool()
_run_python._config = BioPilotConfig.from_env()

TOOLS = [_run_python] + get_recall_tools()
