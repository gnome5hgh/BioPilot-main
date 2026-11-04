# biopilot/service

## Scope

- 覆盖 `biopilot/service/`：FastAPI 应用的应用服务层。
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
- **service 不写裸 SQL**：读写 `bio_*` 引擎表一律经 `mapper/`。
- **service 不处理 HTTP**：不 import FastAPI；需要退出码语义时抛 `service/errors.py` 的领域异常。
- **状态作用域**：进程级共享量在 `state.py`；每个 FastAPI 应用实例的状态在 `domain/runtime_state.py`，由 `create_app()` 创建并注入。
- **懒加载**：重量组件（RAG、平台客户端、Agent 装配）在方法内导入或由容器注入，导入期不拉重型依赖。
- 新增服务：接口 + 实现 + `container.py` 装配 + controller 依赖，顺序不能省。

## 测试

```bash
conda run -n biopilot python -m pytest tests/api tests/core -q
```
