# web/AGENTS.md

Vue3 + Vite 前端：BioPilot 平台的呈现层。

## Scope

- 本 manifest 约束 `web/` 全部源码；上级规则见根 `AGENTS.md`。
- 前端**不存任何业务数据、不做权限判断**：登录态是 Sa-Token token（axios 拦截器统一带 `satoken` 头），角色只决定「渲染哪些入口」，真正的闸在 server。
- 页面只负责呈现与交互；文件归属、知识库是否收录、引用库边界都由后端字段决定，前端不自行推断。

## 模块定位

- 名称：`biopilot-web`
- 角色：登录/对话（SSE + 思考过程 + 确认弹框）/文件管理/文献搜索/知识库/引用库/技能/定时任务/设置/管理页的 SPA，以及全局常驻的终端面板（宿主 shell，可选开启）。
- 数据通道：全部经 `/api` 前缀 → Vite 代理到 SpringBoot 8080（`vite.config.js` 的 `rewrite` 会剥掉 `/api`）；**没有直连 Python 适配层（8300）的调用**——它是纯内网层。
- 接口路径归属：平台 CRUD（项目/文件/论文/文档/定时任务/文献搜索/引用库/检索源管理）由 Java 原生控制器处理；agent 运行时（对话流/确认/知识库检索/终端）由 Java 代理到 Python。前端只认 `/api/...` 路径，不按「谁实现」区分，也不得为了绕过代理而改直连。

## 目录结构

```text
web/src/
├─ main.js / router/   # 入口与路由（登录守卫 + admin 路由守卫）
├─ api/auth.js         # Pinia 用户态 + axios 实例（satoken 头、401 跳登录）
├─ stores/chat.js      # 会话/项目/当前会话/消息/用量（侧栏与对话页共享）
├─ stores/terminal.js  # 终端面板开关（全局一块面板、一条会话）
├─ components/         # AppSidebar / MarkdownView / FilePreviewModal / TerminalPanel / ToastHost / ConfirmDialog
├─ utils/              # time（本地时间）/ toast / confirm / errors / files（原文读取、预览分类、下载）
└─ views/              # Chat / Store / Papers / Literature / KB / Citations / Settings / Admin / Login / MainLayout
```

## 硬规则

- **SSE 用 fetch 流式读**（axios 不支持流式读取）：`/api/agent/chat/stream` 的帧契约是 `content`/`reasoning`/`tool_start`/`tool_end`/`confirm`/`done`/`error`，**`done` 恒发**——以它收尾才允许复用连接；断开即视为取消（重连重发），不做断点续传。
- **思考过程不落库**：`reasoning` 帧只实时追加到当前回答上方；历史会话只回放最终回答，不要在前端自行持久化思维链。
- **确认弹框**：收到 `confirm` 帧暂停渲染后续 token，展示 `tool_name/risk_level/cause/side_effects/params` 后由用户裁决，POST `/api/agent/chat/confirm` 回传；300 秒无操作服务端自动拒绝，前端倒计时只作展示。
- **会话标识**：`conversation_id` 由前端生成（`crypto.randomUUID()`）并经 `X-Conversation-Id` 头携带；换会话必须换 id，不复用。会话归属只在草稿态可选（发送后只读）。
- **上传**：multipart `FormData` 直接交给 axios（**不要手动设 Content-Type**，会丢 boundary）；PDF ≤200MB、其他文件 ≤100MB；同名文件由后端 409 拦截，前端只展示原因。
- **预览/下载**：带 `satoken` fetch 成 blob 再预览或触发下载；不要拼裸 URL 直接 `window.open`（会丢鉴权头）。预览统一走 `components/FilePreviewModal.vue` + `utils/files.js`，新页面不要复制一套 fetch/objectURL/类型分流逻辑。
- **对话附件卡片**：用户消息的附件来自发送时的快照与 `/chat/history` 的 `attachments` 字段，渲染在气泡上方并可点击预览；不要在发送后清空本地附件时连带清掉已入消息的副本。
- 错误提示读 `R` 包络的 `msg` 或 `detail`；401 统一跳登录，403 显示无权限，不吞成静默失败。
- **危险操作统一二次确认**：使用 `utils/confirm.js`，不要再用 `window.confirm/prompt/alert`。
- **终端面板是全局单例**：`TerminalPanel` 挂在 `MainLayout`，关闭只隐藏；服务端按 `user_id`
  复用同一条 shell，切换会话看到的必须是同一份终端内容。客户端输入用 JSON 帧
  （`input`/`resize`），服务端回原始输出；不要为每个会话/页面新建终端。
- 终端是否可用读 `/agent/terminal/config`；`runtime.allow_host_shell=false` 时展示提示，
  不要偷偷回退到别的执行通道。宿主 shell 拥有服务账号权限，共享部署保持关闭。

## 常用命令

```bash
cd web
npm run dev       # 5173，开发模式（/api 代理 8080）
npm run build     # 产物在 dist/
```

## Routing

- 上级：根 `AGENTS.md`
- 对话帧契约与确认语义：ADR 0012；页面与引擎能力的对应关系见 `docs/learning/14-多用户Web平台.md`
