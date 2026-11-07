# bio-literature

## Scope

- 覆盖文献检索与导入：Europe PMC 内置源、MCP 检索源（`bio-common-mcp`）、结果聚合与去重、
  OpenAlex 开放获取解析、PDF 下载校验，以及「搜索结果 → 论文库」的导入编排。
- 文献检索源的管理员配置（`bio_literature_mcp_server`）在本模块；通用 MCP 协议与连接
  生命周期在 `bio-common-mcp`，本模块只做文献 provider 适配。
- 导入结果落论文库（`bio_paper` + OSS），复用 `bio-file` 的 `PaperService` 公开方法。

## Module Positioning

- 角色：`business-domain`
- 职责：把多个检索源统一成 `PaperCandidate`，给前端文献页与 Python agent 提供同一个检索结果。
- 不做论文目录 CRUD、不做文件下载/删除、不碰索引状态（文件资产归 `bio-file`，状态唯一落点在引擎）——`/internal/literature/fetch-pdf` 只返回字节，不登记论文库。

## Directory Structure

- `controller/` — `LiteratureController`（前端 `/api/v1/literature/*`）、
  `InternalLiteratureController`（agent `/internal/literature/search`）、
  `LiteratureMcpAdminController`（ADMIN `/api/v1/admin/literature/sources`）
- `domain/` — `PaperCandidate` / `SearchQuery` / `LiteratureSearchResult` /
  `LiteratureMcpServer`（检索源配置行）
- `dto/` — 管理端请求/视图（密钥只回显「是否配置」）
- `mapper/` — `LiteratureMcpServerMapper`
- `service/` — 接口：`LiteratureSearchService`（聚合/去重/截断）、`LiteratureImportService`（下载+登记）、
  `LiteratureMcpConfigService`（配置 CRUD/热重连/试连）；`service/impl/` — 对应实现
- `service/provider/` — `LiteratureProvider` 接口、`EuropePmcProvider`、`McpPaperProvider`

## Core Logic

- **一个入口，两种调用方**：前端 `/api/v1/literature/search` 与 agent
  `/internal/literature/search` 共用 `LiteratureSearchService`；后者从 Sa-Token 登录过滤中
  排除，由 `InternalTokenFilter` 校验 token 与 `X-User-Id`。
- **provider 只负责映射**：每个源把自己的响应映射成 `PaperCandidate`；超时/非 2xx/解析失败
  抛异常，由聚合层记入 `errors`，不返回静默空列表。单个源失败不拖垮整体。
- **MCP 只接结构化源**：`McpPaperProvider` 调 paper-search-mcp 的 `search_papers`（返回
  structured papers 列表），只做字段映射与年份过滤；不解析散文。管理员新增的 server 必须
  声明 `adapter=paper_search` 才会进入文献检索。
- **连接是软依赖**：启动时异步连接，单个 server 失败只标记 unhealthy，Europe PMC 兜底照常
  返回；配置增删改触发异步热重连，不在请求线程里等子进程。
- **密钥不回显**：`env_json` / `headers_json` 只告诉前端「是否已配置」；编辑时留空表示保持
  原值，空对象表示清空。
- **下载安全**：PDF 只经 `SafePdfFetcher`（仅公网、逐跳校验重定向、`%PDF` 魔数、200MB 上限）。
- **标题来源**：用检索元数据标题；取不到时由 `PaperService` 保持空串，绝不回退文件名。
- **失败语义**：无开放获取/下载失败抛 422 + 可操作文案，不静默降级为空结果。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken/mcp` 与 `bio-file`（仅 `PaperService`）。
- `bio-common-mcp` 提供通用 MCP 客户端；本模块不得自己写协议/传输层。
- 被 `bio-admin` 聚合启动；Python agent 通过 `/internal/literature/search` 消费。

## Core Commands

```bash
cd server
mvn -q -DskipTests install
mvn test -pl bio-admin -q
```
