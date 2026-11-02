# agents

## Scope

- 覆盖 `agents/` Agent 插件目录：每个子目录是一个可被注册表发现的 agent 插件。
- 每个插件的具体能力以它自己的 `AGENT.md` 与 `tools.py` 为准，本文件只定义契约与边界。

## Module Positioning

- 角色：`plugin-root-manifest`
- 职责：以「一个 agent = 一类产物的责任人」为判据组织领域角色，每个角色用一个目录声明它的契约、边界与工具。

## Directory Structure

- `supervisor/` — 调度主管：拆解任务、派发子 agent、汇总回答（持有 spawn + 只读召回，不持有执行类工具）
- `paper-agent/` — 论文域：检索、下载、读 PDF 与图表
- `note-agent/` — 笔记域：基于指定 PDF 起草结构化笔记
- `research-agent/` — 选题域：语料盘点、综述与缺口、选题卡、研究计划
- `review-agent/` — 审查域：笔记审查、选题产物审查（文献检索与筛选由 paper-agent 自己完成）
- `rag-agent/` — 语料索引域：检索、入库、删除后收敛、索引体检
- `memory-agent/` — 记忆域：记忆读写与未读清单
- `bio-agent/` — 数据分析域：沙箱代码执行（唯一持有 `run_python` 的角色）、数据检查、统计与差异分析、单细胞流程、可视化与报告入库

## Responsibilities

- 声明每个角色的身份、边界、能力、交付契约与方法启发式。
- 声明每个角色可派发的子角色（`allowed_spawns`）与它实际装配的工具。
- 承接「流程」以外的部分：**具体做法沉在 skill 里**，这里只写契约与指向。

## Core Logic

- **判据是「一个 agent = 一类产物的责任人」**：每个领域角色独占自己那类产物的读写，其余角色需要时**派发**它，而不是自己装工具。只读召回（会话检索、工具结果回取）是例外：它不产生领域产物，装配给所有 agent。`supervisor` 只编排，不持有任何执行类工具，工具面是 spawn + 只读召回。
- **通用铁律不重复写**：诚实性协议、交付契约语义、协作语义都已下沉到全 agent 共有的行为基座（`biopilot/core/agent/constants/base_prompt.py`）。`AGENT.md` 只写角色特有契约。
- **权限最小化**：`allowed_spawns` 由派发工具在运行时强制（它同时是可派发清单的派生来源）；叶子角色不递归派发；`supervisor` 不装 skill 工具，这是代码级红线。
- **一类产物一个责任人，工具面不重复**：沙箱执行只归 `bio-agent`（`run_python` 是它的独占工具）。不要再建一个纯「代码执行」的平行角色——它的工具面必然是 bio-agent 的子集，supervisor 在清单里看到两个同类目标只会选错；需要跑代码就派 bio-agent。
- **命名一律 `<域>-agent`**，`supervisor` 是唯一例外（它是编排层，不是领域责任人）。

## Key Entry Points

- 各 `agents/<name>/AGENT.md` — 契约与启发式（frontmatter 含名字、描述、可派发清单）
- 各 `agents/<name>/tools.py` — 模块级工具列表
- `biopilot/core/agent/services/registry.py` — 插件发现的唯一入口
- `biopilot/core/agent/constants/base_prompt.py` — 全 agent 共有的行为基座

## Usage And Change Notes

- **每个插件恰好两个文件**：`AGENT.md`（YAML frontmatter + Markdown 正文）与 `tools.py`（模块级工具列表）。多余的辅助文件不会被加载。
- **`name` 必须与目录名一致**，`allowed_spawns` 只能引用已存在的角色。这两条注册期不校验，写错要到运行时才暴露。
- **正文是契约，不是流程**：派发类角色用五段式（身份 / 边界 / 能力 / 交付契约 / 方法启发式），审查角色按角色裁剪。**不在 `AGENT.md` 里写跨 agent 的编排序列**——编排由 LLM 运行时自主决定。
- **流程沉在 skill 里**：写笔记、写选题计划、三类审查的具体步骤在 `.biopilot/skills/` 的流程 skill 中，`AGENT.md` 只写契约并指向它；产物标准（模板）作为 skill 的资源随流程分发，审查方持有自己那一份。
- **权限最小化**：`allowed_spawns` 与风险档位由框架强制，不靠提示词自律。
- **产物落点「用户指定优先，否则 config 默认」**：默认落各自的 config 根（笔记 / 选题产物 / 工作区下载的 PDF 三类），但任务文本点名了保存位置就落那里——**用户的原话到不了子 agent**，supervisor 负责把那个绝对路径原样拼进子任务文本。改了落点要清掉旧稿，同一份产物不留两份。
- **论文库与知识库归平台侧**：agent 下载只落工作区，不登记网页论文库、不自动进知识库——上传/文献导入、加入知识库、删除与收录决定都由用户在网页完成。笔记/研究计划等成稿经 `save_document` 入库文档编辑器；网页文档的删除也在平台侧，agent 只删本地稿。
- **「问用户」不是工具**：子 agent 不能在子任务中途向用户提问——它把缺口写进**最终回答**（配置问询回调的同步确认与此无关，那是风险档位触发的策略升级）。需要用户给信息时，写进最终回答并结束本轮，由 supervisor 决定是否转达。
- **子 agent 的结果经结构化通道回传**：调度方拿到的是带状态（成功 / 失败 / 超时 / 被拒）、摘要与 digest 的结构化结果。**同一会话内同一角色连续两次非成功，结果里会追加强指令**「勿再派发，改用向用户请示」——这是防死循环的兜底，不要绕过它硬重试。
- **新增一个角色要做的**：建目录 → 写 `AGENT.md` + `tools.py` → 在 `config.agents.timeouts` 补一条自己的超时 → 在本文件上面那份清单里补一行。**漏补超时会静默吃类默认的 120s**（那是留给未登记类型的兜底），不要指望有人提醒。

## Dependencies And Collaboration

- 每个角色声明自己的工具；装配层（`biopilot/cli/services/assembly.py`）决定谁装哪些工具与回调。
- 角色之间不直接调用，全部经 supervisor 派发。
- 角色的 `description` 会被自动收进**每个可派发角色**的 system 消息里的可派发清单——清单由该角色自己的 `allowed_spawns` 派生，没有 `allowed_spawns` 的叶子角色不生成该块。派发方按能力选型，**没有「意图 → 子 agent」映射表要维护**。

## Investigation Rule

1. 先读目标角色的 `AGENT.md`（契约与启发式），再看 `tools.py`（实际能力），最后才看装配层。
2. 角色拿到或拿不到某个工具，看装配层；派发被拒看 `biopilot/tools/orchestration/spawn.py`；插件没被发现看 `biopilot/core/agent/services/registry.py`。
3. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/agents -q
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/agents -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 运行时与注册：[`../biopilot/core/AGENTS.md`](../biopilot/core/AGENTS.md)
- 运行时 skill 体系：[`../.biopilot/AGENTS.md`](../.biopilot/AGENTS.md)

## References

- [`supervisor/AGENT.md`](supervisor/AGENT.md)
- [`AGENT.md` 与 `tools.py` 的加载实现](../biopilot/core/agent/services/registry.py)
- [`../biopilot/core/agent/constants/base_prompt.py`](../biopilot/core/agent/constants/base_prompt.py)
