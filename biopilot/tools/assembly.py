"""make_tools：工具装配——实例化工具并注入配置。

提示与强制分离：工具描述里的目录提示只帮助 LLM 定位产物目录，真正的强制边界在
安全中间件（绝对路径 + 敏感路径黑名单）。本模块只负责把「类」实例化为工具、
复用已实例化工具，并把 ``BioPilotConfig`` 注入 ``_config``。
"""
from biopilot.config import BioPilotConfig
from biopilot.core.tool import Tool

__all__ = ["make_tools"]


def make_tools(config: BioPilotConfig, tool_items: list[type[Tool] | Tool]) -> list[Tool]:
    """装配工具列表，兼容「类」与「已实例化工具」两种传参。

    类（如 ReadFileTool 等无参原子工具）经 cls() 实例化；已实例化工具（如
    SpawnSubAgentTool(agent_timeouts=...)——需要构造参数，无参 cls() 会抛
    TypeError）直接复用同一实例。isinstance(item, type) 判定类为「可实例化」，
    否则视为现成实例。

    Args:
        config: BioPilotConfig，注入给工具的配置。
        tool_items: list[type[Tool] | Tool]，工具类或已实例化工具。

    Returns:
        装配好的 Tool 实例列表（已注入 _config）。
    """
    tools = []
    for item in tool_items:
        # 类走无参实例化；现成实例直接复用——两分支共用后续注入逻辑
        tool = item() if isinstance(item, type) else item
        # 文件工具已改为平台 id/名字，不再向描述里注入本地目录提示。
        tool._config = config
        tools.append(tool)
    return tools
