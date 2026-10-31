"""mcp 域的层间契约对象：``McpToolSpec``（工具描述）、``ServerStatus``（观测状态）。"""
from biopilot.core.mcp.domain.dto.server_status import ServerStatus
from biopilot.core.mcp.domain.dto.tool_spec import McpToolSpec

__all__ = ["McpToolSpec", "ServerStatus"]
