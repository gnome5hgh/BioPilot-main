# biopilot/service

## Scope

- 覆盖 `biopilot/service/`：FastAPI 应用的**请求核心逻辑层与全系统组装根**。
- 与 `engine/*/services/` 区分：这里是 Web 运行时编排（SSE、附件、设置、知识库索引、删户、调度），`engine/` 里的是 agent 领域引擎。

## 结构

- `*_service.py` — 每个服务一个 `abc.ABC` 接口。
- `impl/*_service_impl.py` — 实现类。
- `container.py` — `ServiceContainer` 与 `build_services()`。
- `state.py` — 进程级共享状态（整合队列、模型选择、索引 singleflight、定时任务去重）。
- `errors.py` — 领域异常，由 `api/exception_handlers.py` 统一映射。
- `config_helpers.py` — 配置派生路径的薄封装。

## 规则

- **一个服务一个接口**：controller 只依赖接口，具体实现放 `impl/`。
- **只依赖模块适配层**：engine 的 import 只允许 `<模块>`（根别名）或 `<模块>.adapters.*`；application/domain 私有不可见（守护测试锁死）。装配只调各模块 `build_xxx`（`build_memory` / `build_middlewares` / `build_intent` / `build_skill_source` / `build_agent`）。
- **不写裸 SQL**：引擎表读写经 `mapper/`（纯委托模块适配层）或直接调模块适配层的会话查询。
- **service 不处理 HTTP**：不 import FastAPI；需要退出码语义时抛 `service/errors.py` 的领域异常。
- **状态作用域**：进程级共享量在 `state.py`；每个 FastAPI 应用实例的状态在 `runtime_state.py`（本包根），由 `create_app()` 创建并注入。
- **懒加载**：重量组件（RAG、平台客户端、Agent 装配）在方法内导入或由容器注入，导入期不拉重型依赖。
- 新增服务：接口 + 实现 + `container.py` 装配 + controller 依赖，顺序不能省。

## 测试

```bash
conda run -n biopilot python -m pytest tests/api tests/core -q
```
