# biopilot/engine/memory

## Scope

- 覆盖 `engine/memory/`：Letta 记忆栈的移植——MySQL 持久化、记忆块与会话消息、上下文压缩、记忆整合。
- 根 manifest 的两条硬红线（SQL 是真相源、读—改—写必须走一次持锁事务）在本层同样成立，这里写本包特有的。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：为 agent 提供跨轮记忆——可编辑的记忆块、可回放的会话消息、上下文压缩与记忆整合。

## Directory Structure

```text
memory/
├─ constants/    # 工具名集合与块的播种文案
├─ domain/entity/ # 压缩产物：Summary（10 节，第 9 节硬约束、第 10 节截止时间）
├─ domain/dto/   # 整合编辑指令契约：MemoryEdit / MemoryEditBatch（LLM 结构化输出，不落库）
├─ schemas/      # 表实体与持久化模型：块 / 记忆 / 消息 / Agent 状态
├─ storage/      # MySQL 持久化（连接池、表结构、增量迁移、命名锁）
├─ common/       # 领域异常（并发写冲突、块字符上限、整合指令校验失败、编号定位失败）
└─ services/     # 四个职责模块：blocks（块存储与编辑语义，在 block_manager.py）
                 #   + session 管理器（message/agent_manager.py）+ compaction.py + consolidation.py
                 #   （整合 + 轮末 debounce 队列）
```

## Responsibilities

- 落盘全部会话消息，并按 in-context 窗口回放（Recall 完整）；消息按 `session_id` 分组，同一会话的 supervisor 与子 agent 共享分组、各自独立 `agent_id`。
- 提供记忆块的增删改查、版本快照与并发保护。
- 在窗口过长时压缩 in-context（只改窗口，不删 SQL 行）。
- 每轮收尾把新对话排进后台 debounce 队列，空闲窗口后整合进记忆块。

## Core Logic

- **SQL 是唯一真相源**：记忆块只存数据库；历史原话不回溯，硬约束与截止时间由摘要第 9、10 节逐字保留。
- **块写入是持锁的原子读—改—写 + 写入 CAS**：追加/替换类操作把「读旧值→算新值→写回」整段放进一次事务（未经该入口直接写库，会让两个并发写者互相抹掉）。写前留历史快照（供撤销），只读块拒绝读写，块长有上限。
- **压缩只动 in-context 窗口，永不删 SQL 行**：旧摘要并入下一次摘要输入重摘（窗口恒一份最新摘要、多次压缩不累积），保留近期尾部；摘要是 10 节（前 8 节叙述 + 第 9 节硬约束 + 第 10 节截止时间），不携带其余用户原话，原话不作回溯；并保持 tool 消息与它对应的结果成对，别留下孤儿。摘要生成失败时保持原窗口，不拿空摘要替换历史。
- **整合是后台 debounce 队列**：轮末只 enqueue（按会话合并，默认 30s 静默窗口、300s 最大延迟），退出/SIGINT/异常路径必须 flush；整合算法本身仍是游标 + 行级编辑，队列不承载消息。
- **边界约束在摘要第 9、10 节**：硬约束逐条原话、截止时间只在用户明确说过时出现，两者分开成节渲染；它们随摘要一起参与下一次重摘（靠集成指令「不丢已确立的约束」维持），没有独立的快照消息、标记或预算账本。空边界渲染为「（无）」，不触发重调。
- **记忆整合每轮收尾跑一次，空批次即 NOOP**：本轮没有新消息就不调模型。输入是「游标之后的新消息 + **全部可写块的当前值**」——喂旧值是「不产生矛盾条目」的前提，不要为了省 token 只喂增量。
- **整合产出的是行级指令，不是整块重写**：新增 / 按快照编号替换 / 删除，整块重写仅限特定两个块。目标分册名由代码按「类型 + 当天日期」拼装、写满自动续号；编号跨整个分册家族（含往日分册）连续，定位不到就报错，不降级成新增；空掉的分册整块删除——这样「全量喂旧记忆」的总量才有界。
- **旧行靠编号定位，编号是快照地址而非应用时下标**：提示里每行行首的 `[n]` 与「块 + 整行原文」在同一趟渲染里配对，应用时按原文校验。别改成「应用时按当前内容数第 n 行」——LLM 调用期间块可能被别的写者改过，那样会删错行且无任何异常。
- **失败处理是不对称的**：抽取阶段失败要保留游标、下次重试（连败几次后强制推进防死锁）；应用阶段**已有编辑落盘**时照常推进游标（重放会产生重复写入），**一条都没落盘**时保留游标重试（与失败类型无关）。编号定位失败无副作用，在推进前先补一次修复轮（重新渲染编号、跳过复述的已落地指令）。改整合流程时别把这条弄反。
- **同轮即时生效**：每轮开头重建记忆块并替换 head，所以同一轮里改过的块，下一轮模型调用就能看见。改 head 构造顺序时别破坏这个时机。

## Key Entry Points

- `storage/` — 库、表结构与增量迁移
- `services/block_manager.py` — 块 CRUD、CAS、写前快照与编辑语义（重写/插行/替换/补丁/增删改名）
- `services/message_manager.py` / `services/agent_manager.py` — 会话状态：消息落盘与回放、AgentState 与窗口 id
- `services/compaction.py` — 上下文压缩（10 节摘要、旧摘要并入重摘、预算水填）
- `services/consolidation.py` — 记忆整合 + 轮末 debounce 队列（`MemoryConsolidator` / `ConsolidationQueue`）

## Usage And Change Notes

- **给已有表加列，必须同时登记到增量迁移表**：建表脚本只管新库。**漏登记的症状是老库读写时报「没有那一列」，新库上完全测不出来**——所以这类改动要拿旧库试一次。
- **落盘不做 JSON 类型猜测**：持久化消息的正文恒为字符串或空，别按内容形状去猜类型。响应信封以 JSON 一列存放，旧行为空是正常的，不要当成脏数据。
- 长期记忆的只读工具在 `biopilot/tools/recall/memory_read.py`（装配给所有 agent）；写入统一由 `MemoryConsolidator` 完成，不向 agent 暴露写工具。本包只提供管理器，不提供工具封装。

## Dependencies And Collaboration

- 消费方：`engine/agent`（in-context 窗口与压缩）、`tools/recall/`（长期记忆只读 + 工具结果回取）、`api`（轮末 enqueue 与停服 flush）。
- 与 `engine/llm` 的关系是单向的：消费它的消息类型做落盘与回放。
- 与 RAG 无耦合：记忆检索是 SQL，不用向量。

## Investigation Rule

1. 先读本文件，再按问题落到具体服务。
2. 库、表结构与增量迁移看 `storage/`；块读写、并发控制与编辑语义看 `services/block_manager.py`；会话状态看 `services/message_manager.py` 与 `services/agent_manager.py`；压缩看 `services/compaction.py`；整合与轮末队列看 `services/consolidation.py`。
3. 排查「改了没生效」先确认改动是否走了持锁入口；排查老库报错先看增量迁移登记。
4. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/memory -q
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/memory -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)（engine manifest）
- 设计依据：ADR 0004（记忆系统）
- 工具封装与装配：[`../../tools/AGENTS.md`](../../tools/AGENTS.md)、[`../../../agents/AGENTS.md`](../../../agents/AGENTS.md)

## References

- [`storage/`](storage/)
- [`domain/entity/`](domain/entity/)
- [`domain/dto/`](domain/dto/)
- [`services/block_manager.py`](services/block_manager.py)
- [`services/message_manager.py`](services/message_manager.py) / [`services/agent_manager.py`](services/agent_manager.py)
- [`services/compaction.py`](services/compaction.py)
- [`services/consolidation.py`](services/consolidation.py)
- [`schemas/`](schemas/)
