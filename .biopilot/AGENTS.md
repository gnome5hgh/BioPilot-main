# .biopilot

## Scope

- 覆盖 `.biopilot/` 用户级数据目录：**运行时数据根**的默认位置，并承载随仓库分发的意图知识库。
- 入库的只有静态资产：本 manifest、`intent/`；其余子目录都是运行期产物，已由 gitignore 覆盖。
- 用户技能不在这里：技能包由平台管理（Java `bio-skill` + OSS `users/<uid>/skills/`），引擎在会话装配时物化到 `<workspace>/users/<uid>/skills/`。

## Module Positioning

- 角色：`asset-and-runtime-root-manifest`
- 职责：同时承载「要分发给谁」的静态资产（意图知识库）与「跑起来才有」的运行期数据（记忆、审计、会话历史、索引状态、服务卷）。

## Directory Structure

```text
.biopilot/
├─ intent/         # 意图知识库（入库，随仓库发布，有 manifest）
├─ memory/         # 记忆库
├─ security/       # 审计落盘（按天轮转的 JSONL）
├─ session/        # REPL 输入历史
├─ rag/            # 索引状态文件（带配方哈希）与按用户隔离的语料镜像
├─ users/          # 按用户隔离的运行期工作区（上传附件、技能缓存等）
├─ run/            # 本地启动脚本的 pid 与日志
├─ citations/      # 引用库导出等运行期产物
└─ infra/          # 依赖服务（Milvus / MinIO）的数据卷
```

## Responsibilities

- 作为意图知识库的分发根，供运行时装载。
- 作为运行期数据根，收拢记忆、审计、会话历史、索引状态、按用户工作区与服务卷。
- 用 gitignore 边界把「资产」与「产物」分开。

## Core Logic

- **只有静态资产入库**：往本目录下新增子目录时先想清楚它是不是运行期产物——是，就补进 gitignore；不是，才允许进版本库。
- **`security/` 与 `infra/` 受硬拦**：路径权威按前缀拦掉这两个目录的读写（审计防篡改、服务卷不许 agent 碰）。工作区根改到别处时，这两条保护要跟着配——改路径不补规则等于把门敞开。
- **意图知识库随仓库发布、路径锚仓库安装根**：它由装载器做 fail-closed 校验，**不随运行数据根的重定向而搬家**——它是内容资产，不是运行时数据。

## Key Entry Points

- `intent/` — 意图知识库的两份文件（判定口径与示例、高精度规则）
- `memory/` — 记忆库
- `security/` — 审计落盘
- `users/` — 按用户隔离的运行期工作区（技能缓存在 `users/<uid>/skills/`）

## Usage And Change Notes

- **技能体系见 [`biopilot/core/skills/AGENTS.md`](../biopilot/core/skills/AGENTS.md)**：运行时发现与用户技能物化的唯一说明；内置流程已并入各 agent 的 `AGENT.md`，不再有 skill 资产根。
- **运行期数据可以丢**：清空或重建下面的运行期目录只影响历史与索引，不改变任何代码事实。但它也不是事实源——排查时不要拿它当依据。
- 依赖服务的数据卷在 `infra/` 下；清空它会连图表原图一起清掉，重建后要重跑索引。
- `.agents/skills/` 是给编码代理用的技能，与 BioPilot 运行时的用户技能是两条不相干的线。

## Dependencies And Collaboration

- 被 `biopilot/core/intent/rules/`（装载知识库）、`biopilot/core/memory/`、`biopilot/core/security/middleware/audit.py`、`biopilot/core/rag/`、`biopilot/core/skills/`（用户技能缓存路径）消费。
- 运行数据根的位置由运行时配置的 `workspace` 决定，本目录是它的默认值。

## Investigation Rule

1. 先确认要查的是「资产」还是「产物」：资产看 `intent/`，产物只在用户明确要求排查时看。
2. 意图知识库装载报错看 [`biopilot/core/intent/rules/`](../biopilot/core/intent/rules/)；用户技能不生效看 [`biopilot/core/skills/AGENTS.md`](../biopilot/core/skills/AGENTS.md)。
3. 运行数据根的具体子目录名以配置与存储实现为准，不要凭记忆猜。
4. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
python -m pytest tests/core -k "skill or config" -q
```

## Verification

```bash
python -m pytest tests/core -k "skill or config" -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 意图知识库创作规则：[`intent/AGENTS.md`](intent/AGENTS.md)
- Skill 运行时（用户技能物化与发现）：[`../biopilot/core/skills/AGENTS.md`](../biopilot/core/skills/AGENTS.md)
- 意图知识库装载：[`../biopilot/core/intent/AGENTS.md`](../biopilot/core/intent/AGENTS.md)

## References

- [`intent/`](intent/)
- [`../biopilot/core/skills/AGENTS.md`](../biopilot/core/skills/AGENTS.md)
- [`../.gitignore`](../.gitignore)
