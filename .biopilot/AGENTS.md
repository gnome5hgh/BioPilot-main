# .biopilot

## Scope

- 覆盖 `.biopilot/`：随仓库分发的静态资产目录，同时是运行期数据根的**默认位置**。
- 入库的只有静态资产：本 manifest、`intent/`；`infra/` 是依赖服务的数据卷，不入库。
- 运行期数据（外置工具结果、scratch、research/analysis 产物等）写在 `runtime.workspace` 下。它默认指向本目录（`.biopilot`），也可用 `BIOPILOT_RUNTIME_WORKSPACE` 覆盖到仓库外。**RAG 索引状态在 MySQL、平台论文原文在 OSS、笔记在文档编辑器，都不落这里**。本地启动脚本的 pid 与日志固定在 `run/`，不随 workspace 重定向。
- 按用户隔离的派生缓存（附件本地副本、技能物化）由 `runtime.user_cache_dir` 决定；空值回退 `<workspace>/user-cache`，相对路径按仓库安装根解析。它全部可从 OSS/MySQL 重建。
- 用户技能的内容真相在平台（Java `bio-skill` + OSS `users/<uid>/skills/`），引擎只在会话装配时物化到 `<user_cache>/<uid>/skills/`。

## Module Positioning

- 角色：`asset-and-runtime-root-manifest`
- 职责：承载「要分发给谁」的静态资产（意图知识库）与依赖服务的数据卷；运行期产物只是默认落在这里，可被重定向到仓库外。

## Directory Structure

```text
.biopilot/
├─ intent/         # 意图知识库（入库，随仓库发布，有 manifest）
├─ infra/          # 依赖服务（MySQL / Milvus / MinIO）的数据卷（不入库）
├─ run/            # start.sh/stop.sh 的 pid 与日志（不入库）
├─ user-cache/     # 按用户隔离的派生缓存：附件副本、技能物化（不入库，可随时清）
└─ AGENTS.md
```

运行期数据根下的子目录由存储实现决定（常见 `tool-results/`），不要在本文件里抄一份清单。`user-cache/` 在本目录只是「相对路径按安装根解析」的本地配置结果；RAG 索引状态不在这里（见 `bio_rag_index_state` 表），平台论文也没有本地副本。

## Responsibilities

- 作为意图知识库的分发根，供运行时装载。
- 作为依赖服务数据卷的挂载点。
- 默认承接运行期数据；被重定向后只保留静态资产与服务卷。

## Core Logic

- **只有静态资产入库**：往本目录下新增子目录时先想清楚它是不是运行期产物——是，就由 gitignore 的 `.biopilot/*` 覆盖；不是，才用反选允许进版本库。
- **`infra/` 受硬拦**：路径权威按前缀拦掉数据卷的读写。运行数据根可被重定向到仓库外，但 `infra/` 恒在安装根下——保护按安装根额外兜一层，不随 workspace 漂走。
- **意图知识库随仓库发布、路径锚仓库安装根**：它由装载器做 fail-closed 校验，**不随运行数据根的重定向而搬家**——它是内容资产，不是运行时数据。

## Key Entry Points

- `intent/` — 意图知识库的两份文件（判定口径与示例、高精度规则）
- `infra/` — MySQL / Milvus / MinIO 的数据卷（清空即删数据）

## Usage And Change Notes

- **技能体系见 [`biopilot/core/skills/AGENTS.md`](../biopilot/core/skills/AGENTS.md)**：运行时发现与用户技能物化的唯一说明；内置流程已并入各 agent 的 `AGENT.md`，不再有 skill 资产根。
- **运行期数据可以丢**：清空或重建运行期目录只影响历史与索引，不改变任何代码事实。但它也不是事实源——排查时不要拿它当依据。
- **`infra/` 不能删**：它是 MySQL / MinIO / Milvus 的物理数据目录，删掉等于同时删库与对象存储。依赖服务若改成外部实例，才可以不再使用这里的卷。
- `.agents/skills/` 是给编码代理用的技能，与 BioPilot 运行时的用户技能是两条不相干的线。

## Dependencies And Collaboration

- 被 `biopilot/core/intent/rules/`（装载知识库）与运行时装配（工作区默认值、依赖服务卷路径）消费。
- 运行数据根的位置由运行时配置的 `workspace` 决定，本目录只是默认值；`start.sh` / `stop.sh` 的 pid 与日志固定在本目录的 `run/`（可用 `BIOPILOT_RUN_DIR` 覆盖）。

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
