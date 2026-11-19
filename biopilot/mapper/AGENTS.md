# biopilot/mapper

## Scope

- 覆盖 `biopilot/mapper/`：service 层的请求级数据访问**委托层**。

## Module Positioning

- 角色：`platform-data-delegation`
- 引擎表的 SQL 与操作全部住在各 engine 模块的适配层（`engine/memory/adapters` 的会话查询、`engine/rag/adapters/paper_status.py` 的索引状态）；本层**不再持有任何引擎表 SQL**，逐条方法委托模块适配层。平台侧将来要读平台表时，SQL 才落在这里。

## Directory Structure

- `base.py` — `shared_db()` 转发 memory 适配层的 `MemoryDB.shared()`（进程级共享池）。
- `message_mapper.py` / `agent_state_mapper.py` — 会话与消息的请求级查询/回填，委托 memory 适配层。
- `rag_index_mapper.py` / `rag_paper_status_mapper.py` — 索引状态与删户清理，委托 rag 适配层。

## Responsibilities

- 保持 service 侧的访问点名稳定：service 只调 mapper，不直接 import 引擎表 SQL。
- 引擎表新增访问：先落到模块 adapters，再在本层加同名委托方法（`db` 参数不再出现在签名里）。

## Core Logic

- **纯委托**：本层不得出现 SQL 字符串字面量与 `MemoryDB` 以外的引擎设施；委托目标一律是 `engine/<模块>.adapters`（守护测试锁死）。
- 会话删除走 memory 适配层的复合操作（消息 + 游标 + 状态行一次完成），本层不再拆成两条删除。

## Investigation Rule

数据问题先在模块适配层核对 SQL（memory 的 conversation / rag 的 paper_status），再看本层委托签名，最后看 service 调用方。

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 委托目标：[`../engine/memory/AGENTS.md`](../engine/memory/AGENTS.md) / [`../engine/rag/AGENTS.md`](../engine/rag/AGENTS.md)
