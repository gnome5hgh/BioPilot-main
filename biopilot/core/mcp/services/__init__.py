"""MCP 服务：连接管理（后台事件循环 + 持久会话）与逐工具桥接。

`McpToolSpec` / `ServerStatus`（桥接契约与观测状态）在 `../domain/`，
连接状态枚举在 `../constants/`。
"""
from biopilot.core.mcp.services.bridge import (
    build_mcp_tools,
    collect_mcp_agent_tools,
)
from biopilot.core.mcp.services.client import McpClientManager, McpToolError

__all__ = [
    "McpClientManager",
    "McpToolError",
    "build_mcp_tools",
    "collect_mcp_agent_tools",
]
