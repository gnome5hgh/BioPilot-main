# schema

## Scope

- 覆盖 `biopilot/schema/`：HTTP 请求/响应的 Pydantic 契约（浏览器端点与 `/internal/**`）。
- engine 各模块自己的领域 schema（`engine/memory/schemas/` 等）原地保留，不上收本层（父 manifest 规则）。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：定义 HTTP 进出口的形状；一个 controller 域一个文件。

## Directory Structure

- `chat.py` / `session.py` — 对话流与会话列表契约
- `kb.py` / `model.py` / `settings.py` / `terminal.py` — 知识库/模型/设置/终端
- `internal.py` — `/internal/**` 跨栈契约（Java ↔ Python，不版本化）

## Core Logic

- Pydantic v2 BaseModel；内部入参统一 `ConfigDict(extra="ignore")`——跨栈契约新增字段时旧引擎不炸。
- 响应模型（`response_model=`）就是对外承诺：**必须与 handler 实际返回结构逐字段一致**，多字段会被 Pydantic 过滤、缺字段直接 500。

## Usage And Change Notes

- 新增端点：请求/响应模型进对应域文件，命名跟路由动词走；`/internal/**` 的模型改动必须同步 Java `AgentInternalClient` 的反序列化。
- `internal.py` 是跨栈契约：只加字段不改名，不版本化。
- 模型字段与 engine 领域对象同形时**不共享类型**——HTTP 契约与领域 schema 刻意分层，改一边不影响另一边。

## Dependencies And Collaboration

- 只被 `controller/` 消费；不 import `engine/`、`service/`、`mapper/`。

## Investigation Rule

- 端点 500 且栈指向 Pydantic：先对 response_model 与 handler 实际返回的字段差异。
- 契约对不上：两端各看一份（本层 + Java `AgentInternalClient`）。

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
- 同层：[`../controller/`](../controller/AGENTS.md)（唯一消费方）

## References

- [`../controller/`](../controller/AGENTS.md)
