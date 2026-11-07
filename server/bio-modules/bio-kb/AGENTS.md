# bio-kb

## Scope

- 覆盖知识库的**管理面**：哪些论文进入检索语料（`kb_enabled` 勾选与移出）、失败重试
  与标题变更重建的入口（通知引擎）、知识库概览统计与论文清单（索引状态只读展示）。
- RAG 的索引、检索、切块、嵌入与**索引状态**（`bio_rag_paper_status`，引擎独占写）在
  Python 引擎；本模块不读 Milvus、不解析 PDF、不写任何索引状态。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_file` 的 `kb_enabled` 勾选真相（唯一写入口）；清单/概览以 LEFT JOIN
  引擎状态表的方式**只读**索引状态；重试/标题变更经 `/internal/kb/sync` 携带论文 id
  通知引擎。`bio_file` 的身份/文件/书目列只读（用显式 `user_id` 的 SQL，不借 `bio-file` 的 mapper）。
- 调用方有两类：浏览器（勾选、看概览与清单）与引擎（`/internal/kb/sync` 唤醒）。

## Directory Structure

- `controller/` — `KbPaperController`（清单与勾选）、`KbOverviewController`（概览）
- `service/` — 接口：KbPaperService（清单与勾选）/ KbOverviewService；`service/impl/` — 对应实现
- `dto/` — `KbPaperView`（字段与文件管理页的论文视图一致）

## Core Logic

- **勾选是唯一真相**：勾选/移出只写 `kb_enabled`；未勾选的行一律按「未加入」展示，
  状态行残留的 indexed/chunk_count 不外露。
- **索引状态只读**：清单 LEFT JOIN `bio_rag_paper_status`（跨栈读取已在
  `server/AGENTS.md` 登记）；状态机的全部语义（queued→indexing→indexed/failed、
  索引期间移出即拒绝落盘）由引擎在其状态表上就地保证。
- **重试与重建是通知不是写库**：`retry` 与标题变更钩子发 `/internal/kb/sync`
  （携带 `retry_paper_ids` / `requeue_paper_ids`），由引擎重排自己的状态行。
- **概览统计**：复用 `KbPaperService.list` 的归一化结果；collection/embedding/
  running/last_run 经 `/internal/kb/runtime` 取，引擎不可达时回落空值。
- **路径契约**：`/api/v1/kb/papers`、`/api/v1/kb/status`。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken`；**不依赖其他业务模块**。
- 被 `bio-admin` 聚合启动；勾选变更经 `/internal/kb/sync` 唤醒引擎索引器。
