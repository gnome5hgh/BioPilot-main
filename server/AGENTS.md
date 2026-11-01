# server/AGENTS.md

SpringBoot 3.5 服务端（Java 21）：BioPilot 的鉴权、业务表与内网代理层。

## Scope

- 本 manifest 约束 `server/` 全部模块；进入子目录无更近的 manifest。
- 改引擎侧（Python）之前去读 `biopilot/AGENTS.md`；两端共守的信任边界与存储布局在根 `AGENTS.md` 硬红线与 ADR 0013。

## 模块定位

- 名称：`biopilot-server`
- 角色：多用户平台的**唯一鉴权与业务真相层**——注册/登录/登出/资料、角色两档（ADMIN/USER）、登录日志、管理端（用户/审计）、以及到 Python 适配层（127.0.0.1:8300）的内网代理。
- 不做的事：不实现 agent 编排/记忆/检索（引擎的事）；不做页面（web 的事）；对 SSE 流不缓冲不重组、不设应用层超时。

## 目录结构

```text
server/
├─ bio-admin/     # 启动类 BioPilotApplication + 全部控制器（Auth/UserAdmin/AdminGuard/AgentProxy）+ Sa-Token/MyBatis 配置 + application.yaml
├─ bio-modules/   # 业务域聚合器：bio-system（用户/角色/登录日志）、bio-project（项目域）
├─ bio-common/    # bio-common-core：R 响应体 / ServiceException / GlobalExceptionHandler / PageResult
└─ script/sql/    # 建库与种子 SQL（sys_* 表；容器首启由 docker/mysql-init 等效执行）
```

## 硬规则

- **信任边界的出口侧**：登录态里的 userId 即真相，调适配层必带 `X-User-Id` 头；代理目标只允许回环/内网地址。
- **行级 user_id 过滤由 MyBatis-Plus 租户插件统一注入**（`TenantLineInnerInterceptor`）：业务表**不许手写 where 补过滤**（漏一处就是越权读）；豁免表（无 user_id 列的 `sys_role` 等全局表）以插件配置为准。
- **HTTP 客户端锁死 HTTP/1.1**：Java HttpClient 默认的 h2c 升级头（`Upgrade: h2c`）会被 uvicorn 按协议升级处理并**吞掉请求体**——任何新建代理端点共用同一 client 时不得改回默认。
- **口令只存 BCrypt 摘要**；`SysUser.password` 标注 `@JsonIgnore`，任何响应不得带出摘要。
- **异常语义**：业务失败抛 `ServiceException`（`R.fail` 带文案）；未映射路径 404、方法不支持 405、上传超限 413——不许被全局兜底吞成 500。
- **管理接口一律 `@SaCheckRole("ADMIN")`**；鉴权注解放控制器，不放前端约定。
- 新表建表 SQL 同步维护两处：`script/sql/`（人工初始化）与 `docker/mysql-init/`（容器首启）；两份必须等价。

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
