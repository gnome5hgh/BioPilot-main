# biopilot/api

## Scope

- 覆盖 `biopilot/api/`：FastAPI 应用装配层（默认 `127.0.0.1:8300`）。
- 路由处理器不在这里，在 `biopilot/controller/`；业务编排在 `biopilot/service/`。
- 上游规则见根 `AGENTS.md` 的「Python 与 Java 的职责边界」与 `biopilot/AGENTS.md`。

## 模块定位

- 角色：`fastapi-assembly`
- 职责：建 `FastAPI` 实例、挂 `APIRouter`、注册依赖/异常映射/生命周期，并暴露进程启动函数。
- **不是业务层**：不写 SQL、不装配 Agent、不实现知识库编排。

## 文件职责

- `app.py` — `create_app()` 工厂与 `run_server()` 启动函数。
- `deps.py` — `require_user` / `require_internal` 与 `get_services` / `get_runtime` 依赖。
- `router.py` — 汇总全部 controller 的 `APIRouter`。
- `lifespan.py` — 启动后台回收/对账，停服 flush 整合队列并结束终端 shell。
- `exception_handlers.py` — 服务层与配置层异常 → HTTP 响应。
- `assembly.py` / `settings.py` / `shell.py` — 仅保留为旧导入路径的薄壳，实现已迁到 `service/impl/`。

## 分层约定

- `api → controller → service → mapper → common/engine/tools`；本层只依赖 controller 与 `service/container.py`。
- 新增端点：在 `controller/` 加路由，在 `schema/` 加请求/响应模型；**不要在 `app.py` 里堆处理器**。
- 新增服务：在 `service/` 写 ABC、`service/impl/` 写实现，在 `service/container.py` 装配；controller 通过 `Depends(get_services)` 取用。

## 信任边界（不变）

- 所有用户态端点必须要求 `X-User-Id`，缺失即 403（fail-closed）；不二次鉴权，物理前提是只绑回环/内网。
- `/internal/*` 额外要求 `X-Internal-Token`；配置了 `BIOPILOT_INTERNAL_TOKEN` 时缺失或错误即 403，生产必须配置。
- SSE 契约：帧类型含 `token` / `tool` / `round` / `confirm` / `done` / `error`；`done` 帧恒发（含异常路径）；客户端断开映射为取消 run。
- 确认等待由策略引擎计时（默认 300 秒自动拒绝），不依赖 SSE 连接存活。
- 错误一律降级为文本；阻塞调用经 `asyncio.to_thread`；知识库只读端点等锁超限快速返回 409。

## 允许新增的路由类别

- 对话运行时：`/chat/stream`、`/chat/confirm`、`/chat/context-usage`、会话取消/删除。
- 知识库运行时：`/kb/reindex`、`/kb/search`、`/kb/papers/{id}/chunks`。
- 引擎领域产物：`/terminal/*`、`/ws/terminal`。
- 引擎配置：`/settings*`、`/models*`。
- 内部调用：`/internal/kb/*`、`/internal/schedule/run`、`/internal/users/*`。

## 禁止新增

- 平台文件目录 CRUD、定时任务定义 CRUD、文献搜索与导入、用户/角色/项目管理与鉴权。
- 技能管理：归 Java `bio-skill`；本层只在会话装配时只读表并取包物化。

## 关键入口

- `app.py` — `create_app()` / `run_server()`
- `deps.py` — 身份头校验与服务容器
- `router.py` — 路由汇总
- `lifespan.py` — 生命周期
- `../main.py` — 进程启动类

## 测试

```bash
conda run -n biopilot python -m pytest tests/api -q
```
