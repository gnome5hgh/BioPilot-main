# bio-catalog

## Scope

- 覆盖论文目录、数据文件、文档编辑器三个平台文件能力。
- 平台文件管理 HTTP CRUD 归本模块；Agent 侧的 `save_document` 只转发
  `/internal/documents/save`，写入仍由本模块完成（同一张表与 OSS 键约定）。
- 删户时的平台数据清理（论文/文件/文档/引用/项目/定时任务行 + OSS 对象）在本模块。
- 文献搜索与导入不在本模块，见 `bio-literature`（导入只调本模块 `PaperService.ingest`）。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_paper` / `bio_file_upload` / `bio_document` 的全部列与 OSS 生命周期；
  同名检查；为文献导入提供已下载 PDF 的登记入口；维护 `bio_paper` 的索引状态机；
  知识库概览统计（只读 `bio_paper`）。
- **`bio_paper` 单写者**：勾选/移出、状态复位与强制重建在同一条 UPDATE 里；引擎索引过程中的
  `indexing` / `indexed` / `failed` 经 `/internal/kb/{normalize,indexing,result}` 上报，
  强制重建经 `/internal/kb/requeue-all` 复位，均由本模块落盘。引擎不再直接写 `bio_paper`。
- **文件字节出口**：`/internal/attachments/{kind}/{id}` 按 `(user_id, id)` 取回本人论文/数据
  文件；`/internal/files/artifacts` 登记 agent 分析产物（允许跨 run 同名）。

## Directory Structure

- `controller/` — Paper / File / Document / KB paper / KB overview 控制器，以及
  `InternalDocumentController`（agent 成稿入库）、`InternalAttachmentController`
  （附件字节）、`InternalFileController`（分析产物）、`InternalKbStateController`
  （索引状态机）
- `domain/` — 三张表的实体
- `mapper/` — MyBatis-Plus Mapper（`*ForAgent` 方法跳过租户插件：`bio_document`
  的成稿入库、`bio_paper`/`bio_file_upload` 的内部按 (user_id, id) 取行）
- `service/` — PaperService / UploadedFileService / DocumentService / FileCatalogService /
  KbStateService（索引状态机）/ KbOverviewService（知识库概览）/ PlatformUserDataService（删户清理）
- `dto/` — 对前端输出的 snake_case 视图、内部附件内容

## Core Logic

- **对象一致性方向**：创建时对象先落 OSS、行后写；删除时行先删、对象后删。
- **同名检查**：`FileCatalogService` 当前查三张表；后续引入 `bio_user_file` 唯一键后改为插入冲突即 409。agent 分析产物**不做**同名检查（跨 run 重名正常）。
- **索引状态机归本模块**：`KbStateService` 是 `bio_paper` 索引列的唯一写者。勾选/移出与状态复位同一条 UPDATE；结果落盘要求 `kb_enabled=1 AND index_status='indexing'`，索引期间被移出的论文返回 applied=false，由引擎撤回向量与镜像。强制重建先经 `requeueAll` 把所有勾选行置 `queued`。
- **知识库概览归本模块**：`KbOverviewService` 只读 `bio_paper` 统计（与 `PaperView` 同一套归一化）；collection/embedding/running/last_run 经 `AgentInternalClient.kbRuntime` 取，引擎不可达时回落空值，统计照常返回。
- **索引对账**：引擎每轮索引与启动时以 `bio_paper` 为真相核对向量库（孤儿块删除、块数漂移重建）；本模块不直接读 Milvus。
- **内部调用（出站）**：`AgentInternalClient` 必须带 `X-User-Id`（配置了 token 时带 `X-Internal-Token`）；状态已在数据库写好，只调 `/internal/kb/sync` 唤醒索引器。
- **内部调用（入站）**：`/internal/**` 由 `InternalTokenFilter` 校验；成稿入库走
  `DocumentService.saveByName`，附件/论文取行走 `*ForAgent` mapper（显式 user_id、跳过租户插件，
  因为内部调用没有登录态）。
- **删户**：`PlatformUserDataService.purge` 先删平台表行、再删 OSS 对象；引擎数据由 Python
  清理，账号由 `sys_user` 最后删。
- **路径契约**：控制器路径保持 `/agent/papers|files|documents|kb/papers`，前端不改。
- **对外公开服务**：`PaperService.ingest(...)` 供 `bio-literature` 登记已下载 PDF；其余模块不得直接使用本模块 mapper/entity。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken/oss`；不依赖其他业务模块的 mapper/entity。
- 被 `bio-admin` 聚合启动。

## Core Commands

```bash
cd server
mvn -q -DskipTests install
mvn test -pl bio-admin -q
```
