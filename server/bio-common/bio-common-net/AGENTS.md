# bio-common-net

## Scope

- 安全出网：外部 URL 校验（`UrlGuard`）与带逐跳校验的下载（`SafeHttpFetcher` / `SafePdfFetcher`）。
- 主代码纯 JDK，不依赖 Spring——不依赖 `bio-common-web` 的模块（如 `bio-common-mcp`）也能窄依赖进来。

## Module Positioning

- 角色：`shared-capability`
- 职责：所有「外部内容带来的 URL」的出网安全——Java 侧外部抓取（文献导入、`/internal/literature/fetch-pdf`）的唯一出口。

## Core Logic

- **只校验外部 URL，不做全局过滤器**：管理员配置的内部服务地址（MCP 检索源、引擎回调、推理端点）必须能连内网，不归本类管——不要把这里套到配置化端点上。
- `UrlGuard.validateExternal`：scheme 仅 http/https，硬拦 `metadata.google.internal` 与 `169.254.169.254`；`getAllByName` 后逐地址拒绝 any-local/回环/链路本地/私网（site-local）/组播，并显式补 IPv6 ULA `fc00::/7`（`isSiteLocalAddress` 只覆盖 `fec0::/10`）；解析失败 fail-closed。
- `SafeHttpFetcher.fetch`：重定向手动跟随、每一跳都过校验（校验真实 GET 链而非 HEAD 预解析链——两者路径可能分叉）、响应体按 `maxBytes` 流式截断（Content-Length 超限先拒绝）、总时间预算压单跳超时。
- 异常两分：`IllegalArgumentException` = 地址/内容不合法（确定性，端点映射 422）；`IllegalStateException` = 网络/HTTP/重定向失败（瞬时，端点映射 502）。
- 已知边界如实记：DNS rebinding 的 TOCTOU（校验时解析一次、连接时再解析一次）未闭合，真要闭合需解析一次并固定 IP 连接，牵涉 TLS SNI，另立任务。

## Dependencies And Collaboration

- 被 `bio-literature` 使用；不依赖任何 Spring 模块。
- 引擎侧对应物：Python 不再抓外部 URL（`fetch_pdf` 调本模块撑起的内部端点）；配置端点绑定在 `biopilot/common/net/`，两者语义互补、别混用。
