# server/AGENTS.md

SpringBoot 3.5 服务端（Java 21）：BioPilot 的鉴权、平台业务表与引擎接入层。

## Scope

- 本 manifest 约束 `server/` 全部模块；进入子目录无更近的 manifest。
- 改引擎侧（Python）之前去读 `biopilot/AGENTS.md`；两端共守的信任边界与存储布局在根 `AGENTS.md` 硬红线与 ADR 0012。

## 模块定位

- 名称：`biopilot-server`
- 角色：多用户平台的**唯一鉴权与平台业务真相层**——注册/登录/登出/资料、角色两档（ADMIN/USER）、登录日志、项目管理、文件目录（论文/数据文件/文档的 HTTP CRUD 与 OSS 生命周期）、定时任务管理、文献搜索与导入、MCP 检索源配置、管理端（用户/会话/审计读取），以及到 Python 适配层（127.0.0.1:8300）的内网代理。
- 不做的事：不实现 agent 编排/记忆/检索/切块/嵌入（引擎的事）；不复制 Python 的文件解析/切块逻辑；不做页面（web 的事）；对 SSE 流不缓冲不重组、不设应用层超时。`bio_paper` 的索引状态列由本侧 `bio-kb` 的 `KbStateService` 维护，但状态内容由引擎经内部端点上报。
- 与 Python 的分工、单写者规则与表命名规范以根 `AGENTS.md` 的「Python 与 Java 的职责边界」为准。
- **模块划分按职责，不按页面**：一个模块 = 独立的数据所有权 + 独立的变更理由 + 内聚的对外契约。前端页面可以跨模块（设置页、文件管理页就是如此），不为了 1:1 去拆业务域；`bio-gateway` 是技术适配层（浏览器↔引擎），不是业务域，禁止在其中长业务逻辑。

## 目录结构

```text
server/
├─ bio-admin/     # 纯装配：启动类 BioPilotApplication + HealthController + application.yaml
├─ bio-modules/   # 业务域聚合器（每域 service 包为「接口 + impl/ 实现」）：
│                 #   bio-system（身份与访问：账号/角色/登录日志/删户）、bio-project（课题分组）、
│                 #   bio-file（文件资产：论文/数据文件/文档 + OSS 生命周期 + 书目提取）、
│                 #   bio-kb（检索语料状态：知识库勾选 + 索引状态机 + 概览）、
│                 #   bio-schedule（定时任务定义与调度）、
│                 #   bio-literature（文献检索聚合/导入/MCP 检索源管理）、
│                 #   bio-citation（引用库：勾选/维护/导出 .bib）、
│                 #   bio-skill（用户技能：agentskills.io 标准包安装/启停/更新/卸载 + OSS 包 + 内部取包）、
│                 #   bio-gateway（技术适配层：/api/v1 下的引擎 SSE/终端 WS/透传 + 会话列表）
├─ bio-common/    # 共享基础设施（按 cde-common 分模块）
│  ├─ bio-common-core/     # R / PageResult / ServiceException / 常量 / 通用工具（含标题归一化）
│  ├─ bio-common-web/      # 全局异常兜底 / 内部 HTTP 客户端 / multipart / SSE
│  ├─ bio-common-net/      # 安全出网：外部 URL 校验 + 重定向逐跳校验下载（纯 JDK，PDF 下载/文献导入共用）
│  ├─ bio-common-mybatis/  # MyBatis-Plus / 租户插件 / 分页 / 基础实体
│  ├─ bio-common-satoken/  # Sa-Token 配置与 401/403 异常映射
│  ├─ bio-common-oss/      # MinIO/OSS 客户端
│  ├─ bio-common-pdf/      # PDF 标题/书目提取（PDFBox + DOI/arXiv 查询），平台唯一标题来源
│  └─ bio-common-mcp/      # 通用 MCP 客户端（stdio / streamable-http、连接生命周期、工具调用）
└─ script/sql/    # 建库与种子 SQL（sys_* / bio_* 表；容器首启由 docker/mysql-init 等效执行）
   └─ migrations/ # 存量库迁移（如 2026-11-02-rename-tables.sql；执行前备份）
```

## 硬规则

- **信任边界的出口侧**：登录态里的 userId 即真相，调适配层必带 `X-User-Id` 头；代理目标只允许回环/内网地址。
- **对外 URL 按资源命名，不跟模块名走**：浏览器接口统一 `/api/v1/**`，管理端（`@SaCheckRole("ADMIN")`）统一 `/api/v1/admin/**`，资源用复数与 kebab-case；`/internal/**` 是跨栈契约，不版本化也不改名。模块拆分/改名不得牵动 URL。
- **service 包一律「接口 + `impl/` 实现」**：控制器与跨模块消费者只依赖接口；模块之间只调对方公开接口，不借 mapper/entity。
- **行级 user_id 过滤由 MyBatis-Plus 租户插件统一注入**（`TenantLineInnerInterceptor`）：业务表**不许手写 where 补过滤**（漏一处就是越权读）；豁免表（无 user_id 列的 `sys_role` 等全局表，以及引擎侧需要跨用户读写的 `bio_agent_state` / `bio_security_audit_event`）以插件配置为准。Python 走原生 SQL，不经过插件。
- **拥有的表**：`sys_user` / `sys_role` / `sys_user_role` / `sys_login_log` / `bio_project`，以及 `bio_paper`、`bio_citation`（引用库）、`bio_file_upload`（用户上传 + agent 分析产物）、`bio_document`（HTTP CRUD）、`bio_schedule_task`（任务定义与调度进度）、`bio_literature_mcp_server`（检索源配置）、`bio_skill`（用户技能安装记录，带 `user_id`，引擎只读 `enabled/content_sha`）。文献检索没有结果表，导入复用 `bio_paper`。
- **`bio_paper` 按列分写者**：`bio-file` 写身份/文件/书目/`citation_id` 列（含上传登记时的 `kb_enabled` 初值），并在「标题变更且论文在库」时把该篇置回 `queued`（与书目字段同一条 UPDATE，保证原子）；`bio-kb` 写 `kb_enabled` 的状态迁移与 `indexed/index_status/index_error/indexed_at/chunk_count` 列。两边都不碰对方的列。
- **标题与书目提取归本侧**：`bio-common-pdf` 是平台论文标题/作者/年份/期刊的唯一来源；Python 的 RAG 索引只从 `bio_paper.title` 读取，不再自行推导。
- **读取引擎表只读**：`bio_agent_state`、`bio_message`、`bio_security_audit_event` 等由 Python 写入；Java 只读，除项目删除时清 `bio_agent_state.project_id` 外不得写。租户插件豁免表必须显式按 `user_id` 过滤；新增跨栈读取要在本文件登记。
- **内部调用双向**：Java 调 Python `/internal/*`、Python 调 Java `/internal/*`，两个方向都必须带 `X-Internal-Token` 与 `X-User-Id`；`/internal/**` 从 Sa-Token 登录过滤中排除，由 `InternalTokenFilter` 单独把关，内部端点只绑回环/内网。
- **内部端点清单**：Java→Python 为 `/internal/kb/sync`、`/internal/kb/runtime`、`/internal/schedule/run`、`/internal/users/*`；Python→Java 为 `/internal/literature/search`、`/internal/literature/fetch-pdf`、`/internal/documents/save`、`/internal/attachments/{kind}/{id}`、`/internal/files/artifacts`、`/internal/kb/{normalize,indexing,requeue-all,result}`、`/internal/skills/{name}/package`。
- **HTTP 客户端锁死 HTTP/1.1**：Java HttpClient 默认的 h2c 升级头（`Upgrade: h2c`）会被 uvicorn 按协议升级处理并**吞掉请求体**——所有浏览器透传共用 `bio-gateway` 的 `AgentRelay` 单一 client，不得改回默认或另建 client。
- **口令只存 BCrypt 摘要**；`SysUser.password` 标注 `@JsonIgnore`，任何响应不得带出摘要。
- **异常语义**：业务失败抛 `ServiceException`（`R.fail` 带文案）；未映射路径 404、方法不支持 405、上传超限 413——不许被全局兜底吞成 500。
- **管理接口一律 `@SaCheckRole("ADMIN")`**；鉴权注解放控制器，不放前端约定。
- 新表建表 SQL 同步维护两处：`script/sql/`（人工初始化）与 `docker/mysql-init/`（容器首启）；两份必须等价。
- **表命名**：系统表 `sys_<entity>`，BioPilot 业务表 `bio_<domain>_<entity>`（单数实体名）。平台表 DDL 只在 `script/sql/` 与 `docker/mysql-init/` 维护；Python 的 `_SCHEMA` 只建引擎自己的表。
- 旧库升级走 `script/sql/migrations/` 下的迁移脚本；表名迁移见 `2026-11-02-rename-tables.sql`，执行前备份。

## 常用命令

```bash
cd server
mvn install -DskipTests              # 一次性：库模块进本地仓库（新增依赖/改公共模块后重跑）
cd bio-admin && mvn spring-boot:run  # 启动 8080（reactor 里只有 bio-admin 自己，spring-boot:run 才不会打到库模块）
mvn test -pl bio-admin               # 服务端测试
```

`mvn spring-boot:run -pl bio-admin -am` **会失败**：直接目标调用会在 reactor 每个模块上执行，库模块没有 main class。

## Routing

- 上级：根 `AGENTS.md`
- 信任边界与存储布局：ADR 0012；安全轴（引擎侧）：ADR 0002
- 排障：启动失败先看 MySQL 容器健康与 `application.yaml` 的 DSN；401/403 语义见 SaTokenConfigure 与 SaTokenExceptionAdvice
