# bio-schedule

## Scope

- 覆盖定时任务定义与调度：列表、新建、暂停/恢复、立即执行（改 `next_run_at`）、删除，
  以及每 60 秒的到期扫描与投递。
- 到点执行不在本模块：Java 认领任务后调 Python `/internal/schedule/run`，由引擎跑一遍 agent。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_schedule_task` 的全部列（任务定义 + `last_run_at` / `next_run_at` 进度）。
- 不执行 agent、不读引擎进程内状态；执行结果落在归属会话的 `bio_message`，与平台无关。

## Directory Structure

- `controller/` — ScheduleController（路径保持 `/agent/schedules`）
- `domain/` — `bio_schedule_task` 实体
- `mapper/` — MyBatis-Plus Mapper
- `service/` — ScheduleService（定义维护）、ScheduleDispatchService（到期扫描与投递）
- `dto/` — ScheduleView（snake_case 字段与前端契约一致）

## Core Logic

- **单写者**：Java 独占 `bio_schedule_task`（定义与进度列都写）；Python 不读不写该表。
- **时间格式**：ISO-8601 UTC，带微秒与 `+00:00` 偏移，字符串比较即可排序。
- **认领先于投递**：扫描用 `JdbcTemplate` 跨用户查询（无登录态，租户插件会抛
  `NotLoginException`）；每行以旧 `next_run_at` 做 CAS 更新，只有 rowcount=1 才投递，
  多实例不会重复执行。
- **失败也推进**：认领时即写 `last_run_at` 与新的 `next_run_at`，投递失败只记日志——
  与旧语义一致，防止失败任务每轮重试刷爆。
- **立即执行**：只把 `next_run_at` 提前到当前时刻，由下一轮扫描取走，不直接跑 agent。
- **行级隔离**：控制器路径参与 MyBatis-Plus 租户插件，不手写 user_id 过滤；只有
  调度扫描是显式的系统级跨用户查询。

## Dependencies And Collaboration

- 依赖 `bio-common-core/mybatis/satoken/web`；不依赖其他业务模块。
- 被 `bio-admin` 聚合启动；`@EnableScheduling` 在启动类上。
- 投递用 `AgentInternalClient.runSchedule`（异步、失败只记日志）。

## Core Commands

```bash
cd server
mvn -q -DskipTests install
mvn test -pl bio-admin -q
```
