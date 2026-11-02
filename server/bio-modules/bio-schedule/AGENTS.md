# bio-schedule

## Scope

- 覆盖定时任务定义的平台侧维护：列表、新建、暂停/恢复、立即执行（改 `next_run_at`）、删除。
- 到点执行不在本模块：Python 引擎的调度循环读 `bio_schedule_task` 到期行，调 agent 跑一遍。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_schedule_task` 的任务定义列（name/task/interval_minutes/paused/created_at/next_run_at）。
- 不执行 agent、不读引擎进程内状态；执行结果落在归属会话的 `bio_message`，与平台无关。

## Directory Structure

- `controller/` — ScheduleController（路径保持 `/agent/schedules`）
- `domain/` — `bio_schedule_task` 实体
- `mapper/` — MyBatis-Plus Mapper
- `service/` — ScheduleService
- `dto/` — ScheduleView（snake_case 字段与前端契约一致）

## Core Logic

- **单写者（按列）**：Java 写任务定义；Python 调度器只回写 `last_run_at` / `next_run_at`。
- **时间格式**：ISO-8601 UTC，带微秒与 `+00:00` 偏移——Python 调度器按字符串比较到期。
- **立即执行**：只把 `next_run_at` 提前到当前时刻，不绕过调度器、不直接跑 agent。
- **行级隔离**：`bio_schedule_task` 参与 MyBatis-Plus 租户插件，控制器不手写 user_id 过滤。

## Dependencies And Collaboration

- 依赖 `bio-common-core/mybatis/satoken`；不依赖其他业务模块。
- 被 `bio-admin` 聚合启动。

## Core Commands

```bash
cd server
mvn -q -DskipTests install
mvn test -pl bio-admin -q
```
