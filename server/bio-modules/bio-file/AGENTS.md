# bio-file

## Scope

- 覆盖论文目录、数据文件、文档编辑器三个平台文件能力（文件资产域）。
- 平台文件管理 HTTP CRUD 归本模块；Agent 侧的 `save_document` 只转发
  `/internal/documents/save`，写入仍由本模块完成（同一张表与 OSS 键约定）。
- 知识库勾选与索引状态机不在本模块，见 `bio-kb`；删户清理在 `bio-system`。
- 文献搜索与导入不在本模块，见 `bio-literature`（导入只调本模块 `PaperService.ingest`）。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_paper` 的身份/文件/书目/`citation_id` 列、`bio_file_upload`、`bio_document`
  与三者的 OSS 生命周期；同名检查；桌面标题/书目在入库时提取。
- **`bio_paper` 按列分写者**：本模块写身份/文件/书目/`citation_id` 列（含上传登记的
  `kb_enabled` 初值）；`kb_enabled` 的状态迁移与索引状态列归 `bio-kb`。唯一例外是
  「标题变更且论文在库」时把该篇置回 `queued`——与书目字段同一条 UPDATE，保证原子。
- **文件字节出口**：`/internal/attachments/{kind}/{id}` 按 `(user_id, id)` 取回本人论文/数据
  文件；`/internal/files/artifacts` 登记 agent 分析产物（允许跨 run 同名）。

## Directory Structure

- `controller/` — Paper / File / Document 控制器；`InternalAttachmentController`
  （附件字节）、`InternalFileController`（分析产物）、`InternalDocumentController`（成稿入库）
- `domain/` — 三张表实体；`mapper/` — MyBatis-Plus（`*ForAgent` 跳过租户插件）
- `service/` — 接口：PaperService / UploadedFileService / DocumentService / FileCatalogService
  与 Hook 契约；`service/impl/` — 对应实现
- `dto/` — 对前端输出的 snake_case 视图、内部附件内容

## Core Logic

- **对象一致性方向**：创建时对象先落 OSS、行后写；删除时行先删、对象后删。
- **同名检查**：`FileCatalogService` 查三张表（大小写不敏感）；agent 分析产物**不做**同名检查。
- **标题来源**：入库时由 `bio-common-pdf` 提取并落 `bio_paper.title`；取不到就留空，绝不回退文件名。
- **公开服务**：`PaperService.ingest(...)` 供 `bio-literature` 登记已下载 PDF；`get/getForUpdate`
  供 `bio-citation` 与 `bio-gateway` 做归属校验。其余模块不得使用本模块 mapper/entity。
- **路径契约**：`/api/v1/papers|files|documents`；内部端点保持 `/internal/**`。
- **内部调用（出站）**：状态落库后只调 `/internal/kb/sync` 唤醒索引器。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken/oss/pdf`；不依赖其他业务模块。
- 被 `bio-admin` 聚合启动；被 `bio-literature` / `bio-citation` / `bio-gateway` 单向依赖其接口。
