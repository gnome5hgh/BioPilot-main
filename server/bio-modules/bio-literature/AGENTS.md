# bio-literature

## Scope

- 覆盖文献检索与导入：Europe PMC 搜索、OpenAlex 开放获取解析、PDF 下载校验。
- 导入结果落论文库（`bio_paper` + OSS），复用 `bio-catalog` 的 `PaperService` 公开方法。

## Module Positioning

- 角色：`business-domain`
- 职责：文献搜索（外部元数据源）与「搜索结果 → 论文库」的导入编排。
- 不做论文目录 CRUD、不做文件下载/删除、不写索引状态列——这些归 `bio-catalog` 与 Python 引擎。

## Directory Structure

- `controller/` — LiteratureController（路径保持 `/agent/literature/search|import`）
- `service/` — LiteratureSearchService（Europe PMC）、LiteratureImportService（下载 + 登记）
- 无自有表与 Mapper：写库只经 `bio-catalog` 的 `PaperService.ingest`。

## Core Logic

- **只走公开服务**：不依赖 `bio-catalog` 的 mapper/entity，避免模块间数据层穿透。
- **下载安全**：PDF 只经 `SafePdfFetcher`（仅公网、逐跳校验重定向、`%PDF` 魔数、200MB 上限）。
- **标题来源**：用检索元数据标题；取不到时由 `PaperService` 保持空串，绝不回退文件名。
- **失败语义**：无开放获取/下载失败抛 422 + 可操作文案，不静默降级为空结果。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/satoken` 与 `bio-catalog`（仅 `PaperService`）。
- 被 `bio-admin` 聚合启动。

## Core Commands

```bash
cd server
mvn -q -DskipTests install
mvn test -pl bio-admin -q
```
