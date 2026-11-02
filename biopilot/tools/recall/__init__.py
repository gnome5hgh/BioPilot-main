"""只读召回工具包：长期记忆读取 + 工具结果回取。

召回是读操作，不是领域产物写入。长期记忆的写入统一由后台整合完成，任何 agent
都不持有写工具；本包只提供读取通道，装配给所有需要核对原文或查阅记忆的 agent。
"""
from biopilot.tools.recall.memory_read import MemoryReadTool
from biopilot.tools.recall.read_tool_result import ReadToolResultTool

__all__ = ["get_recall_tools", "MemoryReadTool", "ReadToolResultTool"]


def get_recall_tools() -> list:
    """返回只读召回工具实例列表（长期记忆读取 + 工具结果回取）。

    Returns:
        list[Tool]，两个只读工具。
    """
    return [MemoryReadTool(), ReadToolResultTool()]
