# bio-project

## Scope

- 课题分组：项目的新建、列表、重命名/改简介、删除。
- 项目是会话与文件的归属容器；删除项目不级联删会话，会话退回未分组。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_project` 的全部列。
- 删除项目时清空 `bio_agent_state.project_id` 是**唯一一处 Java 写引擎表**的例外（已在根 manifest 登记）。

## Directory Structure

- `controller/ProjectController` — `/api/v1/projects`
- `service/` — 接口 `ProjectService`；`service/impl/ProjectServiceImpl`
- `domain/` + `mapper/`

## Core Logic

- 行级隔离由租户插件注入；只有删除项目的清理语句是显式 `user_id` 的跨表更新。
- 空名称不覆盖已有名称；计费组是原型字段，只有存储没有逻辑。

## Dependencies And Collaboration

- 依赖 `bio-common-core/mybatis/satoken`；不依赖其他业务模块。
- 被 `bio-admin` 聚合启动。
