"""只读召回工具包：工具结果回取。

召回是读操作，不是领域产物写入；它从记忆写入包里拆出来，便于装配给所有
需要核对工具原文的 agent，而不必为一次回取派发 memory-agent。
"""
from biopilot.tools.recall.read_tool_result import ReadToolResultTool

__all__ = ["get_recall_tools", "ReadToolResultTool"]


def get_recall_tools() -> list:
    """返回只读召回工具实例列表（工具结果回取）。

    Returns:
        list[Tool]，单个只读工具。
    """
    return [ReadToolResultTool()]
