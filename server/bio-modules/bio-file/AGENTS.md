# bio-file

## Scope

- 覆盖论文、数据文件、文档编辑器、分析产物四类平台文件能力（文件资产域），统一落在
  `bio_file` 表，用 `kind` 区分。
- 平台文件管理 HTTP CRUD 归本模块；Agent 侧的 `save_document` 只转发
  `/internal/documents/save`，写入仍由本模块完成（同一张表与 OSS 键约定）。
- 知识库勾选与索引状态机不在本模块，见 `bio-kb`；删户清理在 `bio-system`。
- 文献搜索与导入不在本模块，见 `bio-literature`（导入只调本模块 `PaperService.ingest`）。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_file` 的身份/文件/书目/`citation_id`/`kb_enabled` 列与 OSS 生命周期；
  同名唯一键 `(user_id, name_key)`；论文标题/书目在入库时提取。
- **`bio_file` 按列分写者**：本模块写身份/文件/书目/`citation_id`/`kb_enabled` 列；
  `kb_enabled` 的状态迁移与 `index_*` 索引状态列归 `bio-kb`。标题变更且论文在库时，
  本模块只发 `PaperRequeueHook` 通知，由 `bio-kb` 置回 `queued` 并唤醒引擎。
- **正文只在 OSS**：`bio_file` 只存 `oss_key`/`sha256`/`version`，文档写走版本化对象键 +
  条件更新指针；旧对象进 `bio_oss_gc`，提交后才删。
- **文件字节出口**：`/internal/attachments/{kind}/{id}` 按 `(user_id, id)` 取回本人论文/数据
  文件；`/internal/files/artifacts` 登记 agent 分析产物（允许跨 run 同名）。

## Directory Structure

- `controller/` — Paper / File / Document 控制器；`InternalAttachmentController`
  （附件字节）、`InternalFileController`（分析产物）、`InternalDocumentController`（成稿入库）
- `domain/` — `BioFile` / `BioOssGc` 实体与对象键/命名纯函数；`mapper/` — MyBatis-Plus
  （`*ForAgent` 跳过租户插件，`bio_oss_gc` 整表豁免）
- `service/` — 接口：PaperService / UploadedFileService / DocumentService / OssGcService
  与 Hook 契约（含 `PaperRequeueHook`）；`service/impl/` — 对应实现
- `dto/` — 对前端输出的 snake_case 视图、内部附件内容

## Core Logic

- **对象一致性方向**：创建时对象先落 OSS、行后写；更新时对象先落、条件更新指针、提交后
  删旧对象；删除时行先删、对象交给 `bio_oss_gc`。失败只留无引用对象，绝不留悬挂指针。
- **同名唯一键**：`bio_file` 的 `(user_id, name_key)` 直接裁决，论文/数据文件/文档共用；
  agent 分析产物 `name_key` 为 NULL，**不做**同名检查。
- **标题来源**：入库时由 `bio-common-pdf` 提取并落 `bio_file.title`；取不到就留空，绝不回退文件名。
- **公开服务**：`PaperService.ingest(...)` 供 `bio-literature` 登记已下载 PDF；`get/getForUpdate`
  供 `bio-citation` 与 `bio-gateway` 做归属校验。其余模块不得使用本模块 mapper/entity。
- **路径契约**：`/api/v1/papers|files|documents`；内部端点保持 `/internal/**`。
- **内部调用（出站）**：状态落库后只调 `/internal/kb/sync` 唤醒索引器。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken/oss/pdf`；不依赖其他业务模块。
- 被 `bio-admin` 聚合启动；被 `bio-literature` / `bio-citation` / `bio-gateway` 单向依赖其接口；
  `bio-kb` 通过 `PaperRequeueHook` 接收标题变更通知（本模块不反向依赖 `bio-kb`）。
