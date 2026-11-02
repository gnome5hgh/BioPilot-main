# bio-gateway

## Scope

- 浏览器 ↔ Python 适配层的**全部转发**：SSE 对话流、确认回传、历史回放、上下文用量、
  模型选择、平台设置、技能商店、终端开关、知识库试检索/重建/分块。
- 终端 WebSocket 中继（浏览器 ⇄ SpringBoot ⇄ 引擎 PTY）与用户侧会话列表读取。

## Module Positioning

- 角色：`technical-adapter`（**不是业务域**）
- 职责：守住信任边界（登录态 userId → `X-User-Id`）、统一 HTTP/1.1 与 SSE 转发语义、
  集中维护错误降级；不承载业务规则、不写平台业务表。
- 对话/会话的真相在引擎：本模块只转发；会话列表从引擎表只读（显式 `user_id`）。

## Directory Structure

- `web/AgentRelay.java` — 唯一转发通道（单一 HttpClient，HTTP/1.1 锁死）
- `controller/ChatProxyController` — 对话流、确认、历史、上下文用量、会话删除
- `controller/EngineProxyController` — 模型、终端、设置、技能、知识库试检索
- `controller/SessionController` — 用户侧会话列表（只读 `bio_agent_state`/`bio_message`）
- `config/WebSocketConfig` + `ws/TerminalRelayHandler` — 终端中继

## Core Logic

- **单一 client**：所有透传共用 `AgentRelay` 的 HttpClient；不得改回默认协议或另建 client
  （h2c 升级头会被 uvicorn 吞掉请求体）。
- **SSE 不缓冲不重组**：逐块转发并立即 flush；进入流之前的非 200 响应必须如实带状态码透传
  （JSON 错误体不是 SSE 帧）。`done` 帧由引擎负责恒发。
- **归属校验留在平台侧**：知识库分块读取先经 `bio-file` 的 `PaperService.get` 校验论文归属。
- **路径契约**：`/api/v1/chat/*`、`/api/v1/conversations/*`、`/api/v1/models`、
  `/api/v1/terminal/*`、`/api/v1/admin/settings`、`/api/v1/admin/skills/*`；
  WS 注册在 `/api/ws/terminal`（与 nginx 的 `/api/` 反代同一入口）。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/satoken/mybatis` 与 `bio-file`（仅归属校验）。
- 被 `bio-admin` 聚合启动；不依赖其他业务模块，业务模块也不得依赖本模块。
