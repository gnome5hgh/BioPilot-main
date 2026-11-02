package com.biopilot.common.mcp;

import java.util.List;

/**
 * 一个 MCP server 的观测状态。
 *
 * @param name     server 名
 * @param state    连接状态
 * @param tools    已发现的工具名
 * @param error    最近一次失败原因（成功时为 null）
 */
public record McpServerStatus(
        String name,
        McpConnectionState state,
        List<String> tools,
        String error) {

    public McpServerStatus {
        tools = tools == null ? List.of() : List.copyOf(tools);
    }
}
