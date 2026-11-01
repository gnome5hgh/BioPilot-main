# web/AGENTS.md

Vue3 + Vite 前端：BioPilot 平台的呈现层。

## Scope

- 本 manifest 约束 `web/` 全部源码；上级规则见根 `AGENTS.md`。
- 前端**不存任何业务数据、不做权限判断**：登录态是 Sa-Token token（axios 拦截器统一带 `satoken` 头），角色只决定「渲染哪些入口」，真正的闸在 server。

## 模块定位

- 名称：`biopilot-web`
- 角色：登录/对话（SSE + 确认弹框）/论文库/文档编辑器/文献搜索/知识库/终端/设置/管理页的 SPA。
- 数据通道：全部经 `/api` 前缀 → Vite 代理到 SpringBoot 8080（`vite.config.js` 的 `rewrite` 会剥掉 `/api`）；**没有直连 Python 适配层（8300）的调用**——它是纯内网层。

## 目录结构

```text
web/src/
├─ main.js / router/   # 入口与路由（登录守卫 + admin 路由守卫）
├─ api/auth.js         # Pinia 用户态 + axios 实例（satoken 头、401 跳登录）
└─ views/              # 一页一文件：Chat / Store / Papers / DocEditor / Literature / Terminal / KB / Settings / Admin / Login / MainLayout
```

## 硬规则

- **SSE 用 fetch 流式读**（axios 不支持流式读取）：`/api/agent/chat/stream` 的帧契约是 `token`/`confirm`/`tool`/`round`/`done`/`error`，**`done` 恒发**——以它收尾才允许复用连接；断开即视为取消（重连重发），不做断点续传。
- **确认弹框**：收到 `confirm` 帧暂停渲染后续 token，用户选择后 POST `/api/agent/chat/confirm` 回传；300 秒无操作服务端自动拒绝，前端不要自作主张倒计时覆盖。
- **会话标识**：`conversation_id` 由前端生成（`crypto.randomUUID()`）并经 `X-Conversation-Id` 头携带；换会话必须换 id，不复用。
- **上传**：multipart `FormData` 直接交给 axios（**不要手动设 Content-Type**，会丢 boundary）；大文件上限 200MB 由两端强制，前端只做友好提示。
- 错误提示读 `R` 包络的 `msg`；401 统一跳登录，403 显示无权限，不吞成静默失败。

## 常用命令

```bash
cd web
npm run dev       # 5173，开发模式（/api 代理 8080）
npm run build     # 产物在 dist/
```

## Routing

- 上级：根 `AGENTS.md`
- 对话帧契约与确认语义：ADR 0013；页面与引擎能力的对应关系见 `docs/learning/14-多用户Web平台.md`
