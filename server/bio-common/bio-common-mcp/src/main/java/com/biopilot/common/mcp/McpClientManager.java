package com.biopilot.common.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.modelcontextprotocol.client.McpClient;
import io.modelcontextprotocol.client.McpSyncClient;
import io.modelcontextprotocol.client.transport.HttpClientStreamableHttpTransport;
import io.modelcontextprotocol.client.transport.ServerParameters;
import io.modelcontextprotocol.client.transport.StdioClientTransport;
import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.json.jackson2.JacksonMcpJsonMapper;
import io.modelcontextprotocol.spec.McpClientTransport;
import io.modelcontextprotocol.spec.McpSchema;
import jakarta.annotation.PreDestroy;
import java.net.URI;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * MCP 客户端管理器：把外部 MCP server 的工具调用收成一个通用的 Java 能力。
 *
 * <p>它只负责协议与连接生命周期，不认识文献、论文等业务概念：调用方（如文献 provider）
 * 自己决定调哪个 server 的哪个工具、如何解释结果。stdio 与 streamable-http 两种传输都
 * 由官方 SDK 承担，本类只做配置到 SDK 对象的映射。</p>
 *
 * <p>连接失败是软失败：状态置为 {@link McpConnectionState#FAILED} 并记录原因，不抛给
 * 调用方、不阻塞启动。配置变更时重新连接，旧连接先关闭，避免子进程泄漏。</p>
 */
@Component
public class McpClientManager {

    private static final Logger log = LoggerFactory.getLogger(McpClientManager.class);

    private final Map<String, ManagedClient> clients = new ConcurrentHashMap<>();
    private final Map<String, McpServerStatus> statuses = new ConcurrentHashMap<>();
    private final McpJsonMapper jsonMapper;
    private final ExecutorService connector = Executors.newFixedThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "mcp-connect");
        thread.setDaemon(true);
        return thread;
    });

    public McpClientManager(ObjectMapper objectMapper) {
        this.jsonMapper = new JacksonMcpJsonMapper(objectMapper);
    }

    /** 异步连接：启动与配置变更都不阻塞请求线程。 */
    public void connectAsync(McpServerConfig config) {
        connector.submit(() -> connect(config));
    }

    /** 批量异步重连：先断开已移除的 server，再逐个连接当前配置。 */
    public void reloadAsync(Collection<McpServerConfig> configs) {
        List<String> keep = configs.stream().map(McpServerConfig::name).toList();
        for (String name : List.copyOf(clients.keySet())) {
            if (!keep.contains(name)) {
                disconnect(name);
            }
        }
        for (McpServerConfig config : configs) {
            if (config.enabled()) {
                connectAsync(config);
            } else {
                disconnect(config.name());
            }
        }
    }

    /**
     * 同步连接并发现工具；失败只记状态，不抛异常。
     *
     * @param config server 配置
     */
    public synchronized void connect(McpServerConfig config) {
        disconnect(config.name());
        if (!config.enabled()) {
            return;
        }
        McpSyncClient client = null;
        try {
            McpClientTransport transport = buildTransport(config);
            client = McpClient.sync(transport)
                    .requestTimeout(config.callTimeout())
                    .initializationTimeout(config.connectTimeout())
                    .build();
            client.initialize();
            List<String> tools = new ArrayList<>();
            for (McpSchema.Tool tool : client.listTools().tools()) {
                if (config.allowsTool(tool.name())) {
                    tools.add(tool.name());
                }
            }
            clients.put(config.name(), new ManagedClient(config, client, List.copyOf(tools)));
            statuses.put(config.name(), new McpServerStatus(
                    config.name(), McpConnectionState.CONNECTED, tools, null));
            log.info("MCP server {} 已连接，可用工具 {} 个", config.name(), tools.size());
        } catch (Exception e) {
            if (client != null) {
                closeQuietly(client);
            }
            statuses.put(config.name(), new McpServerStatus(
                    config.name(), McpConnectionState.FAILED, List.of(), e.getMessage()));
            log.warn("MCP server {} 连接失败: {}", config.name(), e.getMessage());
        }
    }

    /**
     * 试连一个 server 并返回状态，不替换线上连接（管理端「测试连接」用）。
     *
     * @param config 待测试的配置
     * @return 连接状态与工具清单；失败带原因
     */
    public McpServerStatus probe(McpServerConfig config) {
        McpSyncClient client = null;
        try {
            client = McpClient.sync(buildTransport(config))
                    .requestTimeout(config.callTimeout())
                    .initializationTimeout(config.connectTimeout())
                    .build();
            client.initialize();
            List<String> tools = client.listTools().tools().stream()
                    .map(McpSchema.Tool::name)
                    .filter(config::allowsTool)
                    .toList();
            return new McpServerStatus(config.name(), McpConnectionState.CONNECTED, tools, null);
        } catch (Exception e) {
            return new McpServerStatus(config.name(), McpConnectionState.FAILED,
                    List.of(), e.getMessage());
        } finally {
            if (client != null) {
                closeQuietly(client);
            }
        }
    }

    /** 断开并移除一个 server（幂等）。 */
    public synchronized void disconnect(String name) {
        ManagedClient managed = clients.remove(name);
        if (managed != null) {
            closeQuietly(managed.client());
        }
        statuses.put(name, new McpServerStatus(
                name, McpConnectionState.DISCONNECTED, List.of(), null));
    }

    /** 某 server 当前可见的工具名；未连接返回空列表。 */
    public List<String> tools(String name) {
        ManagedClient managed = clients.get(name);
        return managed == null ? List.of() : managed.tools();
    }

    /** 某 server 的观测状态；未知 server 按未连接处理。 */
    public McpServerStatus status(String name) {
        return statuses.getOrDefault(name, new McpServerStatus(
                name, McpConnectionState.DISCONNECTED, List.of(), null));
    }

    /** 全部 server 状态（按名称排序，便于管理端稳定展示）。 */
    public Map<String, McpServerStatus> statuses() {
        Map<String, McpServerStatus> out = new LinkedHashMap<>();
        statuses.keySet().stream().sorted().forEach(name -> out.put(name, statuses.get(name)));
        return out;
    }

    /**
     * 调用一个工具；未连接、工具被过滤或协议错误都抛异常，由调用方转成业务错误。
     *
     * @param server server 名
     * @param tool   工具名
     * @param args   工具参数
     * @return 工具结果（结构化与文本双通道）
     */
    public McpToolResult callTool(String server, String tool, Map<String, Object> args) {
        ManagedClient managed = clients.get(server);
        if (managed == null) {
            throw new IllegalStateException("MCP server 未连接: " + server);
        }
        if (!managed.config().allowsTool(tool)) {
            throw new IllegalStateException("MCP 工具不在允许列表: " + server + "/" + tool);
        }
        McpSchema.CallToolResult result;
        try {
            result = managed.client().callTool(
                    new McpSchema.CallToolRequest(tool, args == null ? Map.of() : args));
        } catch (RuntimeException e) {
            // 传输层断开（stdio 子进程崩溃/HTTP 断连）不能继续宣称 CONNECTED：
            // 状态是管理端唯一的可观测信号，必须如实反映失败。
            statuses.put(server, new McpServerStatus(
                    server, McpConnectionState.FAILED, managed.tools(), e.getMessage()));
            throw e;
        }
        StringBuilder text = new StringBuilder();
        if (result.content() != null) {
            for (McpSchema.Content content : result.content()) {
                if (content instanceof McpSchema.TextContent textContent) {
                    if (text.length() > 0) {
                        text.append('\n');
                    }
                    text.append(textContent.text());
                }
            }
        }
        return new McpToolResult(result.structuredContent(), text.toString(),
                Boolean.TRUE.equals(result.isError()));
    }

    @PreDestroy
    public void close() {
        connector.shutdownNow();
        for (String name : List.copyOf(clients.keySet())) {
            disconnect(name);
        }
    }

    private McpClientTransport buildTransport(McpServerConfig config) {
        if ("http".equalsIgnoreCase(config.transport())) {
            URI uri = URI.create(config.url());
            String base = uri.getScheme() + "://" + uri.getAuthority();
            String endpoint = uri.getPath() == null || uri.getPath().isBlank()
                    ? "/mcp" : uri.getPath();
            HttpClientStreamableHttpTransport.Builder builder =
                    HttpClientStreamableHttpTransport.builder(base)
                            .endpoint(endpoint)
                            .jsonMapper(jsonMapper)
                            .connectTimeout(config.connectTimeout());
            if (!config.headers().isEmpty()) {
                builder.customizeRequest(request -> config.headers()
                        .forEach((key, value) -> request.header(key, value)));
            }
            return builder.build();
        }
        ServerParameters parameters = ServerParameters.builder(config.command())
                .args(config.args())
                .env(config.env())
                .build();
        return new StdioClientTransport(parameters, jsonMapper);
    }

    private static void closeQuietly(McpSyncClient client) {
        try {
            client.close();
        } catch (Exception e) {
            log.debug("关闭 MCP 客户端失败: {}", e.getMessage());
        }
    }

    private record ManagedClient(McpServerConfig config, McpSyncClient client,
                                 List<String> tools) {
    }
}
