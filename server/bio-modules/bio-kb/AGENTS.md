# bio-kb

## Scope

- 覆盖知识库的**状态面**：哪些论文进入检索语料（`kb_enabled` 勾选与移出）、索引状态机
  （排队/索引中/成功/失败、对账归一化、失败重试）、引擎状态上报接收、知识库概览统计。
- RAG 的索引、检索、切块、嵌入本体在 Python 引擎；本模块不读 Milvus、不解析 PDF。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_paper` 的 `kb_enabled` 状态迁移与 `indexed/index_status/index_error/indexed_at/chunk_count`
  列；`bio_paper` 的身份/文件/书目列只读（用显式 `user_id` 的 SQL，不借 `bio-file` 的 mapper）。
- 调用方有两类：浏览器（勾选、看概览）与引擎（`/internal/kb/*` 状态上报）。

## Directory Structure

- `controller/` — `KbPaperController`（清单与勾选）、`KbOverviewController`（概览）、
  `InternalKbStateController`（引擎上报：normalize/indexing/requeue-all/result）
- `service/` — 接口：KbPaperService（清单与勾选）/ KbStateService（状态机）/ KbOverviewService；
  `service/impl/` — 对应实现
- `dto/` — `KbPaperView`（字段与文件管理页的论文视图一致）

## Core Logic

- **勾选是唯一真相**：勾选/移出与状态复位在同一条 UPDATE 里；未勾选的行一律按「未加入」展示。
- **状态迁移**：`not_added/queued → indexing → indexed/failed`；成功与失败都要求当前仍是
  `indexing` 且 `kb_enabled=1`——索引期间被移出的论文，结果自然被拒绝。
- **对账**：引擎每轮索引与启动时以 `bio_paper` 为真相核对向量库；本模块只接收结果、不读 Milvus。
- **对账归一化**：`normalize` 把派生列收敛到勾选状态；只有持索引锁的调用方才允许重排遗留 `indexing`。
- **概览统计**：复用 `KbPaperService.list` 的归一化结果；collection/embedding/running/last_run
  经 `/internal/kb/runtime` 取，引擎不可达时回落空值。
- **路径契约**：`/api/v1/kb/papers`、`/api/v1/kb/status`；内部端点 `/internal/kb/*`。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken`；**不依赖其他业务模块**。
- 被 `bio-admin` 聚合启动；引擎经 `/internal/kb/*` 上报，Java 经 `/internal/kb/sync` 唤醒索引器。
