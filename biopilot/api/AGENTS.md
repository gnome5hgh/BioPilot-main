# biopilot/api

## Scope

- 覆盖 `biopilot/api/`：Python 引擎的 HTTP/SSE 适配层（FastAPI，默认 `127.0.0.1:8300`）。
- 上游规则见根 `AGENTS.md` 的「Python 与 Java 的职责边界」与 `biopilot/AGENTS.md`。

## 模块定位

- 角色：`agent-runtime-api`
- 职责：把引擎能力暴露成 HTTP/SSE——对话流、确认、上下文用量、知识库检索/索引触发与标题消费、终端、内部调用。
- **不是业务 CRUD 层**：论文/数据文件/文档/定时任务/文献搜索的增删改查归 Java（`server/`）。本层新增端点是最后手段，先判断该能力是否属于 agent 运行时。

## 允许新增的路由类别

- 对话运行时：`/chat/stream`、`/chat/confirm`、`/chat/context-usage`、会话取消/删除。
- 知识库运行时：`/kb/reindex`、`/kb/search`、`/kb/papers/{id}/chunks`。状态概览与论文清单归 Java（`bio_paper` 是真相），本层只读向量库。
- 引擎领域产物：`/terminal/*`、`/ws/terminal`。引用库是平台功能，不在此暴露。
- 引擎配置：`/settings`（有效值 + 字段描述）、`/settings/history`、`/settings/rollback`。ADMIN 守卫在 Java 层；密钥只回显「是否配置 + 末 4 位」。
- 内部调用：`/internal/kb/sync`（唤醒索引）、`/internal/kb/runtime`（供 Java 概览合并的运行时信息）、`/internal/schedule/run`（Java 调度器触发一次定时任务）、`/internal/users/*`（删户数据清理）。

## 禁止新增

- 平台文件目录 CRUD：`/papers/*`、`/files/*`、`/documents/*` 的增删改查与上传下载。
- 定时任务定义 CRUD：`/schedules/*`（Java `bio-schedule`）。
- 文献搜索与导入：`/literature/*`（Java `bio-literature`）。agent 需要检索时只调 Java 的 `/internal/literature/search`，不在本层实现检索。
- 用户/角色/项目管理与鉴权：归 Java。
- 技能管理：安装/启停/更新/卸载与 `bio_skill` 表归 Java `bio-skill`；本层不暴露 `/store/skills` 之类端点，只在会话装配时只读表并用 Java 的 `/internal/skills/{name}/package` 取包物化。

## 硬规则

- **信任边界**：所有用户态端点必须要求 `X-User-Id`，缺失即 403（fail-closed）；不二次鉴权，物理前提是只绑回环/内网。
- **内部端点**：`/internal/*` 额外要求 `X-Internal-Token`；配置了 `BIOPILOT_INTERNAL_TOKEN` 时缺失或错误即 403，生产必须配置。内部端点只允许 Java 调用。
- **SSE 契约**：帧类型含 `token` / `tool` / `round` / `confirm` / `done` / `error`；`done` 帧恒发（含异常路径）；客户端断开映射为取消 run。
- **确认等待**：由策略引擎计时（默认 300 秒自动拒绝），不依赖 SSE 连接存活。
- **错误降级**：工具与中间件错误转成文本/错误帧回传模型或客户端，不绕过 ReAct 循环。
- **阻塞调用进线程**：RAG 检索/分块这类会等锁或走网络的同步调用必须经 `asyncio.to_thread`；在事件循环线程里同步等 RAG 锁会让整个适配层停摆（状态与论文清单等无关请求一起悬挂）。等锁设有上限，索引占用时快速返回 409「正在索引」，不排队阻塞。
- **数据写入**：只写引擎领域表（`bio_agent_state`/`bio_message`/`bio_memory_*`/`bio_security_audit_event`/`bio_config*`）；**不直接 INSERT/UPDATE/DELETE `bio_paper`**，索引结果经 `/internal/kb/{indexing,result}` 上报，强制重建经 `/internal/kb/requeue-all` 复位。`save_document` 只转发 Java `/internal/documents/save`。
- **一致性对账**：MySQL 的 `bio_paper` 是知识库唯一真相。每轮索引与启动时都要对账向量库：不属任何「已加入」论文的块删除；已就绪论文的向量块数与 `chunk_count` 不一致则重建；`failed` 不自动重试（用户重试由 Java 先置 `queued`）。
- **附件解析**：身份只认 body 里的 `file_id`/`paper_id`，字节与文件名由 Java `/internal/attachments/{kind}/{id}` 按 `X-User-Id` 返回；body 里的 `oss_key` 一律忽略（防跨用户读取），本地路径片段先归一化（防穿越）。
- **出站内部调用**：`search_literature`、`save_document`、附件/论文原文取回、分析产物登记、PDF 抓取、索引状态上报都走 `common/platform` 客户端；失败降级为工具文本，不阻塞启动。
- **同名约束**：文件目录的唯一性由 `bio_user_file` 的数据库唯一键保证，不在本层做「先查再插」。

## 关键入口

- `app.py` — `create_app()` 工厂；对话流、会话、知识库、终端、内部端点。
- `assembly.py` — `assemble_web_session()`：唯一的会话对象图装配（配置 → 记忆 → 安全 → 意图 → Agent）。
- `entry.py` — 进程入口：`biopilot` / `python -m biopilot`，`config` 子命令或启动 Web 适配层。
- `shell.py` — 按 `user_id` 复用的宿主终端 PTY 会话。

## 测试

```bash
conda run -n biopilot python -m pytest tests/api -q
```
