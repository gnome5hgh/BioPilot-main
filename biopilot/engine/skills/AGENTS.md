# biopilot/engine/skills

## Scope

- 覆盖 `engine/skills/`：**用户技能**的运行时消费——发现、校验、渐进披露与本地缓存物化。
- 技能的管理面（安装/启停/更新/卸载、`bio_skill` 表与 OSS 包）在 Java 的 `bio-skill` 模块；本包不写管理状态。
- 内置流程（写笔记、选题、两套审查）**不是 skill**：它们写在对应 agent 的 `AGENT.md` 里，模板在该角色 `references/` 下（见 [`agents/AGENTS.md`](../../../agents/AGENTS.md)）。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：把用户安装的 agentskills.io 标准形态包变成 agent 可消费的 L1 清单、L2 正文与 L3 资源。

## Directory Structure

```text
skills/
├─ config/      # SkillConfig：name / description / 正文 / metadata / 目录
└─ services/    # layout.py     用户技能缓存路径
                # registry.py   单根扫描 + frontmatter 校验 + 渐进披露
                # user_skills.py 按 content_sha 物化用户技能缓存
                # assembly.py   merge_tools / apply_pre_approval（工具命名空间）
```

## Responsibilities

- 扫描用户技能缓存目录（`<user_cache>/<uid>/skills/`，缓存根由 `runtime.user_cache_dir` 决定），校验每份 SKILL.md（name 必须等于目录名、description 必填，fail-fast）。
- 提供三级渐进披露：L1 清单注入 head → L2 按需加载正文 → L3 读目录内资源（路径围栏）。
- 把该用户启用的技能包从平台内部端点物化到本地缓存，按 `content_sha` 判断是否需要重拉。

## Core Logic

- **单根扫描**：注册表只接受用户技能缓存目录；点开头的目录（临时物化目录）跳过。
- **标准形态包**：只读 SKILL.md 与资源文件；**不导入 tools.py**（平台不接受该扩展）。
- **缓存不是真相源**：`user_skills` 把 `bio_skill` 的启用行物化成本地目录，`content_sha` 对不上就删了重拉；平台不可达时保留旧缓存、无缓存则该用户暂时没有额外技能，不阻塞对话。
- **按会话构造**：web 会话装配时构建注册表，因此安装/启停在用户下一次对话生效，不需要重启引擎。
- **L1 只列用户技能**：内置流程常驻对应 agent 的提示词，不参与这份清单。

## Key Entry Points

- `services/registry.py` — 发现、校验与 L1/L2/L3。
- `services/user_skills.py` — 用户技能物化与缓存清理。
- `services/layout.py` — 用户缓存路径。
- `services/assembly.py` — 工具命名空间校验（与 agent 工具合并共用）。

## Usage And Change Notes

- **name == 目录名是硬约束**：物化时按 `name` 建目录，安装侧也按 `name` 打包，两边天然一致；放宽会让「按名字加载」的下游一起失准。
- **不要在运行时写管理状态**：启停/来源/版本只读 `bio_skill`；任何写操作都应回到 Java 的 `bio-skill` 模块。
- **用户技能**：建目录（目录名 = frontmatter name）→ 写 SKILL.md → 需要资源时放 `references/`、`assets/`、`scripts/`，由安装通道打包。

## Dependencies And Collaboration

- 被 `engine/agent`（head 注入清单）与 `tools/skills/load_skill`（L2/L3）消费。
- `user_skills` 经 `biopilot/common/platform` 调 Java `/internal/skills/{name}/package` 取包；读 `bio_skill` 只读 MySQL。
- 与 agent 自带的 `references/`（内置流程模板）无关：那是 agent 插件资源，经 `read_reference` 读取。

## Investigation Rule

1. 用户技能不生效先看注册期 fail-fast（通常名字与目录名不一致或缺字段）。
2. 再看 `user_skills` 的物化日志：平台不可达、sha 不一致都会跳过并记 warning。
3. 内置流程不生效看对应 agent 的 `AGENT.md` 与 `references/`，不要往 skill 体系找。
4. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
python -m pytest tests/core -k "skill" -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)（engine manifest）
- 设计依据：ADR 0010（Skill 系统）
- 内置流程与 agent 资源：[`../../../agents/AGENTS.md`](../../../agents/AGENTS.md)
- 管理面：[`../../../server/AGENTS.md`](../../../server/AGENTS.md)

## References

- [`services/registry.py`](services/registry.py)
- [`services/user_skills.py`](services/user_skills.py)
- [`services/layout.py`](services/layout.py)
- [`../../../agents/AGENTS.md`](../../../agents/AGENTS.md)
