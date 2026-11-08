# domain

## Scope

- 覆盖 `biopilot/domain/`：应用层领域对象（dataclass 与 Protocol）。
- HTTP 契约模型不在本层（见 [`../schema/`](../schema/AGENTS.md)）；进程级共享状态不在本层（见 [`../service/`](../service/AGENTS.md)）。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：定义适配层的纯数据结构与最小接口协议，让 service 层不依赖具体传输实现。

## Directory Structure

- `web_config.py` — 适配层配置（监听地址/端口、DSN）
- `web_session.py` — Web 会话装配产物
- `runtime_state.py` — 每个 FastAPI 应用实例私有的运行时状态
- `terminal_socket.py` — 终端 WebSocket 的最小传输协议（Protocol）

## Core Logic

- **纯数据无行为**：只有 dataclass 与 Protocol，不做 IO、不 import FastAPI/SQL 层——服务层因此可脱离具体框架测试。
- **状态两级分界**：每个应用实例一份的（确认 future、并发闸、活动流队列）进 `RuntimeState`；跨实例共享的（singleflight 集合、最近索引结果等进程级单例状态）进 `service/state.py`。放错层会让多 worker 部署时状态串台或丢失。
- `TerminalSocket` 是故意收窄的协议面：服务层只依赖握手/收发/关闭，不依赖 FastAPI 的 `WebSocket` 类型。

## Usage And Change Notes

- 新增实例级状态：加进 `RuntimeState` 并在应用工厂里初始化；确认它真的不该跨实例共享。
- 新增协议面：先写 Protocol 再写实现，服务层只 import 协议。

## Dependencies And Collaboration

- 被 `service/`、`controller/` 消费；不依赖任何其他层（分层的最底端之一）。

## Investigation Rule

- 状态「丢了/串了」先分清它在哪一级（实例级 vs 进程级），再查归属层。

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
- 同层：[`../schema/`](../schema/AGENTS.md)（HTTP 契约） / [`../service/`](../service/AGENTS.md)

## References

- [`../service/state.py`](../service/state.py)（进程级状态对照面）
