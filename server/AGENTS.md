# server/AGENTS.md

SpringBoot 3.5 服务端（Java 21）：BioPilot 的鉴权、业务表与内网代理层。

## Scope

- 本 manifest 约束 `server/` 全部模块；进入子目录无更近的 manifest。
- 改引擎侧（Python）之前去读 `biopilot/AGENTS.md`；两端共守的信任边界与存储布局在根 `AGENTS.md` 硬红线与 ADR 0013。

## 模块定位

- 名称：`biopilot-server`
- 角色：多用户平台的**唯一鉴权与平台业务真相层**——注册/登录/登出/资料、角色两档（ADMIN/USER）、登录日志、项目管理、文件目录（论文/数据文件/文档的 HTTP CRUD 与 OSS 生命周期）、定时任务管理、文献搜索与导入、管理端（用户/会话/审计读取），以及到 Python 适配层（127.0.0.1:8300）的内网代理。
- 不做的事：不实现 agent 编排/记忆/检索/切块/嵌入（引擎的事）；不直接写引擎的 `index_*` 索引状态列；不复制 Python 的文件解析/切块逻辑；不做页面（web 的事）；对 SSE 流不缓冲不重组、不设应用层超时。
- 与 Python 的分工、单写者规则与表命名规范以根 `AGENTS.md` 的「Python 与 Java 的职责边界」为准。

## 目录结构

```text
server/
├─ bio-admin/     # 启动类 BioPilotApplication + 控制器（Auth/UserAdmin/AdminGuard/AgentProxy）+ application.yaml
├─ bio-modules/   # 业务域聚合器：bio-system（用户/角色/登录日志）、bio-project（项目域）、
│                 #   bio-catalog（论文/文件/文档）、bio-schedule（定时任务定义）、bio-literature（文献搜索/导入）
├─ bio-common/    # 共享基础设施（按 cde-common 分模块）
│  ├─ bio-common-core/     # R / PageResult / ServiceException / 常量 / 通用工具
│  ├─ bio-common-web/      # 全局异常兜底 / 内部 HTTP 客户端 / multipart / SSE / SSRF PDF 下载
│  ├─ bio-common-mybatis/  # MyBatis-Plus / 租户插件 / 分页 / 基础实体
│  ├─ bio-common-satoken/  # Sa-Token 配置与 401/403 异常映射
│  └─ bio-common-oss/      # MinIO/OSS 客户端
└─ script/sql/    # 建库与种子 SQL（sys_* / bio_* 表；容器首启由 docker/mysql-init 等效执行）
   └─ migrations/ # 存量库迁移（如 2026-11-02-rename-tables.sql；执行前备份）
```

## 硬规则

- **信任边界的出口侧**：登录态里的 userId 即真相，调适配层必带 `X-User-Id` 头；代理目标只允许回环/内网地址。
- **行级 user_id 过滤由 MyBatis-Plus 租户插件统一注入**（`TenantLineInnerInterceptor`）：业务表**不许手写 where 补过滤**（漏一处就是越权读）；豁免表（无 user_id 列的 `sys_role` 等全局表，以及引擎侧需要跨用户读写的 `bio_agent_state` / `bio_security_audit_event`）以插件配置为准。Python 走原生 SQL，不经过插件。
- **拥有的表**：`sys_user` / `sys_role` / `sys_user_role` / `sys_login_log` / `bio_project`，以及 `bio_paper`（身份/文件列 + `kb_enabled`）、`bio_file_upload`、`bio_document`（HTTP CRUD）、`bio_schedule_task`（任务定义列）。文献搜索无自有表，导入复用 `bio_paper`。
- **读取引擎表只读**：`bio_agent_state`、`bio_message`、`bio_security_audit_event` 等由 Python 写入；Java 只读，除项目删除时清 `bio_agent_state.project_id` 外不得写。租户插件豁免表必须显式按 `user_id` 过滤；新增跨栈读取要在本文件登记。
- **内部调用**：调 Python `/internal/*` 必须带 `X-Internal-Token` 与 `X-User-Id`，禁止绕过；内部端点只绑回环/内网。
- **HTTP 客户端锁死 HTTP/1.1**：Java HttpClient 默认的 h2c 升级头（`Upgrade: h2c`）会被 uvicorn 按协议升级处理并**吞掉请求体**——任何新建代理端点共用同一 client 时不得改回默认。
- **口令只存 BCrypt 摘要**；`SysUser.password` 标注 `@JsonIgnore`，任何响应不得带出摘要。
- **异常语义**：业务失败抛 `ServiceException`（`R.fail` 带文案）；未映射路径 404、方法不支持 405、上传超限 413——不许被全局兜底吞成 500。
- **管理接口一律 `@SaCheckRole("ADMIN")`**；鉴权注解放控制器，不放前端约定。
- 新表建表 SQL 同步维护两处：`script/sql/`（人工初始化）与 `docker/mysql-init/`（容器首启）；两份必须等价。
- **表命名**：系统表 `sys_<entity>`，BioPilot 业务表 `bio_<domain>_<entity>`（单数实体名）；跨栈共享表还要同步引擎侧 schema。
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
- 信任边界与存储布局：ADR 0013；安全轴（引擎侧）：ADR 0002
- 排障：启动失败先看 MySQL 容器健康与 `application.yaml` 的 DSN；401/403 语义见 SaTokenConfigure 与 SaTokenExceptionAdvice
