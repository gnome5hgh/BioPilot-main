# biopilot/engine/tools

## Scope

- 覆盖 `engine/tools/`：**工具域**——Tool 契约（domain）、工具运行时（application）与具体工具实现（adapters）。
- 本包合并了原「契约单件」（engine/tool）与「实现层」（biopilot/tools）：工具实现是模型 tool-call 的入向适配器，与契约同属一个域。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：定义所有工具共同遵守的契约并加载期校验；把能力暴露成模型可调用的工具（声明参数 schema 与安全元数据，结果降级为文本回传）；提供工具运行时上下文与装配工厂。

## Directory Structure

- `domain/` — 契约词汇：`entity/tool.py`（Tool ABC 与安全元数据字段）+ `dto/tool_result.py`（结果载体：正文 + 结构化摘要两条出口）。**暂不设 `bo/` 与 `vo/`**——出现第一个 occupant 再建，不预置空桶。
- `application/` — 工具运行时：`validation.py`（加载期校验）、`runtime_context.py`（ContextVar 运行时绑定）、`offload.py`（大结果外置回调）、`roots.py`（语义根派生）、`assembly.py`（`make_tools` 装配工厂）
- `adapters/` — 具体工具实现（一工具一文件、按域分包）+ 出向存储：
  - `code/` — 沙箱执行：`run_python` / `run_shell`；共用 `sandboxed.py` 的政策组装、产物登记与结果渲染
  - `file/` — 读 / 写 / 编辑 / glob / grep / 读 PDF / 读参考（标题由 Java 提取，本层不推导）
  - `search/` — 文献检索薄转发与 PDF 下载（调 Java `/internal/literature/*`，SSRF 与 `%PDF` 校验在 Java `bio-common-net`）
  - `rag/` — 检索、看图、入库、全量收敛、索引体检（只装配给 `rag-agent`）
  - `vision/` — 图表提取与看图分析
  - `recall/` — 只读召回包（`memory_read` + `read_tool_result`，装配给所有 agent）
  - `review/` — 审查裁决、模板体检
  - `docs/` — 文档保存（经 Java 平台端口）
  - `skills/` — 加载 skill 正文与资源
  - `orchestration/` — 子 agent 派发（唯一的调度工具）
  - `tool_result_store.py` — 大工具结果写 MinIO（本地回退）
- `constants/` — 摘要里跨模块读写的键名（`SUMMARY_TERMINAL` 等）与语义根词表
- **模块公开面（R1，守护测试锁死）**：公开面 = `adapters/api.py`（Tool/ToolResult/校验/runtime_context/make_tools/外置/常用工具类），根 `__init__` 只做它的别名；**spawn 不进 api.py**（反向依赖 agent，按叶子路径单独 import）。

## Responsibilities

- 固定工具的声明面：名字、描述、参数 JSON Schema、执行入口、安全元数据；把「非法声明」变成加载期的 fail-fast。
- 为每个工具实现声明风险档位与参数格式，把工具结果（含各种失败）统一成结构化结果回传模型。
- 提供结构化结果通道，让决策、摘要与领域数据不必挤进给模型看的正文。

## Core Logic

- **安全元数据必填**：风险档、副作用、来源取值来自 `engine/constants/` 的枚举（单一真相源），注册表加载时校验——写错在这里就报错。风险档是策略引擎「问不问」的输入；副作用字段是「谁在写」的判据（写互斥与写围栏共用）；来源字段声明「结果是不是外部数据」（只有读外部数据的工具才声明，全标会让标记变成噪声）。
- **参数级的格式声明是中间件的接管开关**：路径 → 路径权威、内容 → 内容防护、命令 → 命令防护。新工具不需要写安全代码，声明格式即可被接管；声明错格式等于没被接管。
- **装配一律经装配工厂**：`application/assembly.py` 实例化工具类、复用已实例化工具并注入 `_config`。agent 拿到什么工具由装配层决定，工具内部不要自作主张。
- **结果有两条出口**：正文回给模型；结构化摘要给框架用。摘要里跨模块读写的键名是契约，写错一个字符串的后果是功能静默不生效。大工具结果外置：`Tool.max_result_size_chars` 可覆写全局阈值，原文经 `adapters/tool_result_store.py` 写 MinIO，消息里换成带 `tool_call_id` 的指针；外置在 `ToolExecutor` 的 after 钩子之后发生，审计仍看得到原文。
- **子 agent 只能经派发工具调用**：派发闸门全在 `adapters/orchestration/spawn.py`（未知类型 → 白名单 → 同批去重 → 审稿预算 → 每轮上限）。顺序与并行归 supervisor 自主，闸门只兜上限；轮数预算下沉代码，不靠 LLM 自律。
- **失败一律降级为文本**：工具异常转成错误结果回传模型自行决策；依赖的运行时上下文缺失时 fail-safe 返回提示，绝不挂起。
- **平台数据端口已迁 Java**：沙箱产物经 `/internal/files/artifacts` 登记，平台文件字节经 `/internal/attachments/*` 取回，工具不直连 OSS。

## Key Entry Points

- `domain/entity/tool.py` — `Tool` 基类与元数据字段
- `application/validation.py` — 加载期校验
- `application/runtime_context.py` — 工具运行时上下文（记忆管理器 + RAG 用户域）
- `application/assembly.py` — 工具装配工厂（`make_tools`）
- `adapters/orchestration/spawn.py` — 派发工具与五道闸
- `adapters/recall/` — 只读召回包
- `__init__.py` — 契约与常用工具的再导出

## Usage And Change Notes

- 新增工具：在 `adapters/<域>/` 写文件 → 声明安全元数据与参数格式 → 在包 `__init__`（若是常用工具）登记 → 在装配层决定装给谁。**领域写入只装给该领域责任人**，其余角色需要时派发它；只读召回是例外，装给所有 agent。
- 工具的运行时上下文由装配层注入；缺失时要降级为提示，不要抛异常。工具内不要直接构造重量组件（视觉/主模型客户端的执行期自构是登记例外，注入口保留供测试）。
- 方向约束：本包消费 engine 各域包（domain/application/adapters 均可）；各域包**不得** import 本包的 `adapters/`（工具实现），`domain/`、`constants/` 与 `application/`（校验、runtime_context 等运行时协作者）放行。

## Dependencies And Collaboration

- 依赖：`engine.constants`（风险枚举）、`biopilot.common`（frontmatter/paths/net）、`engine.security`（沙箱）、`engine.rag`（检索门面）、`engine.skills`（技能注册表）、`engine.llm`（视觉/看图客户端）、`engine.agent`（仅 `orchestration/spawn.py` 构造子 agent）。
- 被装配：`agents/<name>/tools.py` 声明工具面，`AgentRegistry` 动态加载，`assembly_service_impl` 注入会话级依赖。

## Investigation Rule

1. 工具怎么写、装给谁先读本文件；契约细节看 `domain/entity/tool.py` 的 docstring。
2. 运行时上下文与装配看 `application/`；具体能力按域找 `adapters/<域>/`。
3. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/tools tests/core/test_tool_metadata.py -q
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/tools -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- Agent 插件契约（工具装给谁）：[`../../agents/AGENTS.md`](../../agents/AGENTS.md)

## References

- [`domain/entity/tool.py`](domain/entity/tool.py)
- [`application/runtime_context.py`](application/runtime_context.py)
- [`application/assembly.py`](application/assembly.py)
