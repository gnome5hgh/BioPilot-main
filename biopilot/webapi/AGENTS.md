# biopilot/webapi

## Scope

- 覆盖 `biopilot/webapi/`：Python 引擎的 HTTP/SSE 适配层（FastAPI，默认 `127.0.0.1:8300`）。
- 上游规则见根 `AGENTS.md` 的「Python 与 Java 的职责边界」与 `biopilot/AGENTS.md`。

## 模块定位

- 角色：`agent-runtime-api`
- 职责：把引擎能力暴露成 HTTP/SSE——对话流、确认、上下文用量、知识库检索/索引触发、引用库、终端、内部调用。
- **不是业务 CRUD 层**：论文/数据文件/文档/定时任务/文献搜索的增删改查归 Java（`server/`）。本层新增端点是最后手段，先判断该能力是否属于 agent 运行时。

## 允许新增的路由类别

- 对话运行时：`/chat/stream`、`/chat/confirm`、`/chat/context-usage`、会话取消/删除。
- 知识库运行时：`/kb/status`、`/kb/reindex`、`/kb/search`、`/kb/papers/{id}/chunks`。
- 引擎领域产物：`/citations/*`、`/terminal/*`、`/ws/terminal`。
- 内部调用：`/internal/*`（索引 enqueue/detach/retry/sync、PDF 安全下载等）。定时任务执行不设内部端点：调度循环在本进程内直接读表并调 agent。

## 禁止新增

- 平台文件目录 CRUD：`/papers/*`、`/files/*`、`/documents/*` 的增删改查与上传下载。
- 定时任务定义 CRUD：`/schedules/*`（Java `bio-schedule`）。
- 文献搜索与导入：`/literature/*`（Java `bio-literature`）。
- 用户/角色/项目管理与鉴权：归 Java。

## 硬规则

- **信任边界**：所有用户态端点必须要求 `X-User-Id`，缺失即 403（fail-closed）；不二次鉴权，物理前提是只绑回环/内网。
- **内部端点**：`/internal/*` 额外要求 `X-Internal-Token`；配置了 `BIOPILOT_INTERNAL_TOKEN` 时缺失或错误即 403，生产必须配置。内部端点只允许 Java 调用。
- **SSE 契约**：帧类型含 `token` / `tool` / `round` / `confirm` / `done` / `error`；`done` 帧恒发（含异常路径）；客户端断开映射为取消 run。
- **确认等待**：由策略引擎计时（默认 300 秒自动拒绝），不依赖 SSE 连接存活。
- **错误降级**：工具与中间件错误转成文本/错误帧回传模型或客户端，不绕过 ReAct 循环。
- **数据写入**：只写引擎领域表、`bio_paper` 的索引状态列与 `bio_document`（`save_document` 工具）；不写 Java 的身份/文件列与 `kb_enabled`。
- **同名约束**：文件目录的唯一性由 `bio_user_file` 的数据库唯一键保证，不在本层做「先查再插」。

## 关键入口

- `app.py` — `create_app()` 工厂；对话流、会话、知识库、终端、内部端点。
- `shell.py` — 按 `user_id` 复用的宿主终端 PTY 会话。

## 测试

```bash
conda run -n biopilot python -m pytest tests/webapi -q
```
