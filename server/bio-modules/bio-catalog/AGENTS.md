# bio-catalog

## Scope

- 覆盖论文目录、数据文件、文档编辑器三个平台文件能力。
- 平台文件管理 HTTP CRUD 归本模块；Agent 侧的 `save_document` 工具仍可直接写
  `bio_document`（agent 产物），两者靠同一张表与 OSS 键约定协作。
- 文献搜索与导入不在本模块，见 `bio-literature`（导入只调本模块 `PaperService.ingest`）。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_paper` / `bio_file_upload` / `bio_document` 的身份/文件元数据与 OSS
  生命周期；同名检查；为文献导入提供已下载 PDF 的登记入口。
- 不写 `bio_paper` 的 `index_*` 索引状态列；创建/删除后通过
  `AgentInternalClient` 调 Python `/internal/kb/*`。

## Directory Structure

- `controller/` — Paper / File / Document / KB paper 控制器
- `domain/` — 三张表的实体
- `mapper/` — MyBatis-Plus Mapper
- `service/` — PaperService / UploadedFileService / DocumentService / FileCatalogService
- `dto/` — 对前端输出的 snake_case 视图

## Core Logic

- **对象一致性方向**：创建时对象先落 OSS、行后写；删除时行先删、对象后删。
- **同名检查**：`FileCatalogService` 当前查三张表；后续引入 `bio_user_file` 唯一键后改为插入冲突即 409。
- **索引状态不在这里写**：`index_*` 归 Python `core/rag/services/paper_state.py`。
- **内部调用**：`AgentInternalClient` 必须带 `X-User-Id`（配置了 token 时带 `X-Internal-Token`）。
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
