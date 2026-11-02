# bio-citation

## Scope

- 平台引用库：用户把文件管理里的论文加入引用库、维护库外条目、按样式复制或导出 `.bib`。
- 引用库**不参与 agent 溯源**：agent 不再写 `[来源:...]`，也不读写本表。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_citation` 行 + `bio_paper.citation_id` 的单向关联；加入/移出/论文删除/书目变更的联动。
- 不写 `bio_paper` 的索引状态列（归 `bio-catalog` 的 `KbStateService`）；不参与 RAG 索引与检索。

## Core Logic

- **关联方向**：`bio_paper.citation_id → bio_citation.id`（可空，`ON DELETE SET NULL`）；本表不存 `paper_id`。
- **加入**：事务内锁论文行（`PaperService.getForUpdate`）→ 幂等检查 → 插入条目 → 回写 `citation_id`。
- **移出**：删条目 → 清 `citation_id`（外键存在时自动，应用层再显式兜底）。
- **删除论文**：实现 `PaperDeletionHook`，在同一事务里先删条目再删论文行。
- **书目变更**：实现 `PaperMetadataHook`，标题/作者/年份/期刊改动后同步引用行。
- 元数据优先取 `bio_paper`；缺作者/年份/期刊时用 `bio-common-pdf` 从 OSS 原文提取，标题为空拒绝入库。

## Dependencies And Collaboration

- 依赖 `bio-catalog`（论文查询与 Hook 契约）、`bio-common-pdf`、`bio-common-oss`。
- 被 `bio-admin` 聚合启动；前端路径保持 `/agent/citations/*`。
