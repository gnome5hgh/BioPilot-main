# bio-system

## Scope

- 身份与访问：注册/登录/登出、当前用户资料、角色两档（ADMIN/USER）、登录日志。
- 管理端读侧：用户列表/更新/重置口令、会话总览、登录日志与安全审计事件读取。
- 账号生命周期：删户两阶段（标记删除 → 物理清理）与平台数据清理编排。

## Module Positioning

- 角色：`business-domain`
- 职责：`sys_user` / `sys_role` / `sys_user_role` / `sys_login_log` 的全部列；
  删户时清理各平台表的行与 OSS 对象（显式 `user_id` 的 SQL，不走租户插件）。
- 引擎表（会话/审计）只读；本项目删除外不得写。
- 口令只存 BCrypt 摘要，任何响应不得带出。

## Directory Structure

- `controller/` — `AuthController`（/api/v1/auth/*、/api/v1/users/me）、
  `UserAdminController`（/api/v1/admin/users|roles|conversations|audit/*）、
  `UserDeletionController`（/api/v1/admin/users/{id}/deletion、DELETE /api/v1/admin/users/{id}）、
  `AdminGuardController`（角色注解锚点）
- `service/` — 接口：SysUserService / PlatformUserDataService；`service/impl/` — 对应实现
- `config/StpInterfaceImpl` — Sa-Token 角色数据源
- `domain/` + `mapper/` — 三张账号表实体与 Mapper

## Core Logic

- **删户顺序**：引擎数据（Python `/internal/users/*`）成功 → 平台表行 → OSS 对象 → 最后删账号；
  引擎侧失败不删账号，管理员可重试。
- **标记删除**：先踢下线并停用登录，再通知引擎停掉该账号的工作。
- **登录日志**：成败都记（用户名/用户 id/结果/IP），写入 `sys_login_log`。
- **路径契约**：浏览器接口 `/api/v1/auth/*` 与 `/api/v1/admin/**`（管理端整类 `@SaCheckRole("ADMIN")`）。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/satoken/mybatis/oss`；不依赖其他业务模块。
- 被 `bio-admin` 聚合启动；删户时调适配层内部端点（`AgentInternalClient.postSync`）。
