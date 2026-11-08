# controller

## Scope

- 覆盖 `biopilot/controller/`：全部 HTTP 路由层（浏览器端点与 `/internal/**` 内部端点）。
- 分层规则（依赖方向、controller 的禁止事项）以父 [`../AGENTS.md`](../AGENTS.md) 的 Layering 为准，本文件不复述。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：把 HTTP 请求翻译成对 service 的调用并把结果包成响应；是唯一允许出现 FastAPI 路由装饰器的层。

## Directory Structure

- `chat_controller.py` — 对话 SSE 与确认
- `session_controller.py` — 会话列表（读引擎表）
- `kb_controller.py` — 知识库试检索/分块/重建（浏览器侧）
- `internal_controller.py` — `/internal/**`：kb sync/runtime、定时任务触发、删户两阶段
- `settings_controller.py` / `model_controller.py` — 配置数据面（模型列表/切换）
- `terminal_controller.py` — 终端 WS
- `health_controller.py` — 健康探测

## Responsibilities

- 参数解析、`Depends` 注入、调用 service、返回响应；**不写 SQL、不装配 Agent、不持有业务状态**。
- SSE 只透传 service 产生的帧，不缓冲不重组；`done` 帧恒发（根硬红线）。

## Core Logic

- 全部路由经 [`../api/router.py`](../api/router.py) 汇总；新增 controller 必须在那里挂载。
- 两类鉴权入口：浏览器端点 `require_user`（校验 `X-User-Id` 归属头存在），内部端点 `require_internal`（另验 `X-Internal-Token`）；**头的值不校验**（信任边界，见 ADR 0012）。
- 确认等待、上下文用量等读进程内状态的能力都经 service，不直接摸 `RuntimeState`。

## Key Entry Points

- [`../api/deps.py`](../api/deps.py) — `require_user` / `require_internal` / 服务容器依赖
- [`../api/router.py`](../api/router.py) — 路由汇总
- [`../service/container.py`](../service/container.py) — 可注入的服务

## Usage And Change Notes

- 新增端点：先按根 manifest 的管理面/执行面尺判断是否属于 agent 运行时 → 在本层加路由、在 [`../schema/`](../schema/AGENTS.md) 加请求/响应模型、复用或新增 service ABC；不在路由里堆处理器逻辑。
- 内部端点是跨栈契约：**不改名、不版本化**；请求/响应模型改动要两端同步（Java 侧 `AgentInternalClient`）。
- 改内部模块名要同步 `tests/` 的 monkeypatch 目标（见父 manifest Investigation Rule）。

## Dependencies And Collaboration

- 只依赖 `service/` 与 `schema/`；不直接依赖 `engine/`、`mapper/`（分层硬规则见父）。

## Investigation Rule

1. 端点行为异常：先看本层 handler 做了什么、再看对应 service impl；装配/依赖问题查 [`../api/deps.py`](../api/deps.py)。
2. 文档与代码冲突时以代码为准。

## Core Commands

```bash
/opt/miniconda3/envs/biopilot/bin/python -m pytest tests/api -q
```

## Verification

```bash
/opt/miniconda3/envs/biopilot/bin/python -m pytest tests/api -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 同层：[`../service/`](../service/AGENTS.md) / [`../schema/`](../schema/AGENTS.md) / [`../api/`](../api/AGENTS.md)

## References

- [`../api/app.py`](../api/app.py)（应用工厂）
