# bio-common-mcp

## Scope

- 通用 MCP 客户端：把外部 MCP server（stdio / streamable-http）的工具调用收成 Java 能力。
- 不绑定业务：不认识文献、论文、检索等概念；调用方自己决定调哪个 server 的哪个工具。

## Module Positioning

- 角色：`shared-infrastructure`
- 职责：配置到 SDK 传输对象的映射、连接生命周期、工具发现、工具调用与状态观测。
- 不做：不存配置（配置落业务域表）、不做权限判断、不解析业务结果。

## Directory Structure

- `McpServerConfig` — 单个 server 的通用配置（transport/url/command/args/env/headers/超时/工具名单）
- `McpConnectionState` / `McpServerStatus` — 连接状态与观测结果
- `McpToolResult` — 一次工具调用的结构化 + 文本双通道结果
- `McpClientManager` — 连接/重连/断开、试连、调用、状态汇总

## Core Logic

- **用官方 SDK，不自己实现协议**：`mcp-core` + `mcp-json-jackson2`（Jackson 2；不要用聚合
  `mcp` artifact，它会拉 Jackson 3，与 Spring Boot 3.5 冲突）。
- **连接是软失败**：`connect` 捕获异常并置 `FAILED`，不抛给启动流程；调用方按状态决定是否跳过。
- **异步重连**：管理端增删改配置后调 `reloadAsync`，不在请求线程里等子进程/网络。
- **stdio 是任意命令执行面**：只在受信环境使用，命令与参数由业务域管理员配置并审计；
  HTTP 模式优先。
- **工具名单在此生效**：`allowedTools` 空表示不限制，`disabledTools` 优先；过滤后的工具才
  会出现在状态里，`callTool` 也按同一名单拒绝。

## Dependencies And Collaboration

- 依赖官方 MCP Java SDK、Spring Context、Jackson 2、SLF4J。
- 被 `bio-literature`（文献检索源）使用；后续其他业务需要 MCP 时复用本模块，不另建客户端。

## Core Commands

```bash
cd server
mvn -q -DskipTests install -pl bio-common/bio-common-mcp -am
```
