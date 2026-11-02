package com.biopilot.common.mcp;

import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * 一个 MCP server 的接入配置（通用结构，不绑定数据库与业务域）。
 *
 * @param name           唯一名称（同名覆盖；也是状态与日志里的标识）
 * @param transport      {@code stdio} 或 {@code http}（streamable-http）
 * @param url            http 必填：完整端点，如 {@code http://paper-search-mcp:8000/mcp}
 * @param command        stdio 必填：可执行文件（如 uvx）
 * @param args           stdio 启动参数
 * @param env            stdio 子进程环境变量（可能含密钥，展示时必须脱敏）
 * @param headers        http 请求头（可能含密钥，展示时必须脱敏）
 * @param enabled        是否启用
 * @param connectTimeout 建连与初始化超时
 * @param callTimeout    单次工具调用超时
 * @param allowedTools   工具白名单；空列表表示不限制
 * @param disabledTools  工具黑名单
 */
public record McpServerConfig(
        String name,
        String transport,
        String url,
        String command,
        List<String> args,
        Map<String, String> env,
        Map<String, String> headers,
        boolean enabled,
        Duration connectTimeout,
        Duration callTimeout,
        List<String> allowedTools,
        List<String> disabledTools) {

    public McpServerConfig {
        args = args == null ? List.of() : List.copyOf(args);
        env = env == null ? Map.of() : Map.copyOf(env);
        headers = headers == null ? Map.of() : Map.copyOf(headers);
        allowedTools = allowedTools == null ? List.of() : List.copyOf(allowedTools);
        disabledTools = disabledTools == null ? List.of() : List.copyOf(disabledTools);
        connectTimeout = connectTimeout == null ? Duration.ofSeconds(30) : connectTimeout;
        callTimeout = callTimeout == null ? Duration.ofSeconds(60) : callTimeout;
    }

    /** 该工具是否允许调用：黑名单优先，白名单为空表示不限制。 */
    public boolean allowsTool(String tool) {
        if (disabledTools.contains(tool)) {
            return false;
        }
        return allowedTools.isEmpty() || allowedTools.contains(tool);
    }
}
