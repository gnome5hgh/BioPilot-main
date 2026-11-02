"""memory-agent 的工具装配：9 件记忆读写/管理工具 + 只读召回包。

记忆是一类产物（核心块 + 未读清单），按「一个 worker = 一类产物的责任人」，
它的读写只装配给本角色——其他角色一件不装，想记录只能派发本角色来记，所以
不存在「忘了记账」的静默失败（工具不在别人手里，想漏也漏不掉）。

**为什么要 memory_read**：`memory_replace` 要求给 `old_string`、
`memory_apply_patch` 要求对着当前内容写 diff，两者都以「已经看到当前内容」为
前提；`memory_read` 按标签读块当前值，是定向增改的预读通道，也是核对块现状
的通用读入口。

不给写文件工具：块的写入一律经记忆工具（走 BlockManager 的原子读-改-写 + CAS），
绕开它会失去并发保护与版本历史。
"""
from biopilot.config import BioPilotConfig
from biopilot.tools import GlobTool, ReadFileTool
from biopilot.cli.services.tool_assembly import make_tools
from biopilot.tools.memory import get_memory_tools
from biopilot.tools.recall import get_recall_tools

#: 记忆写入/管理 8 件 + 只读召回包 + 读块内容的只读工具。
# 记忆工具是无状态类、执行时才取运行时上下文，直接实例化；读工具经 make_tools 注入 _config。
TOOLS = get_memory_tools() + get_recall_tools() + make_tools(
    BioPilotConfig.from_env(), [ReadFileTool, GlobTool])
