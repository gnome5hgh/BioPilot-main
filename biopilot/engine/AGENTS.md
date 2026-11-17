# biopilot/engine

## Scope

- 覆盖 `engine/` 核心运行层——按三层架构组织的 agent 系统（领域 / 应用 / 适配）。子包内部实现以源码为准。
- 各子包各有自己的 manifest（见 Routing）；根 manifest 的硬红线在本层同样成立，这里不重复。

## Module Positioning

- 角色：`aggregator-manifest-dir`
- 职责：集中放运行时能力——ReAct 引擎、LLM 接入、记忆、意图、安全、RAG、视觉、工具域（契约 + 运行时 + 实现）与它们共享的契约；本层只负责聚合与分层约束，具体行为由各子包自己定义。MCP 客户端与文献检索归 Java，不在本层。

## Directory Structure

- `agent/` — ReAct 引擎：`application/`（主循环、插件发现、状态容器、执行管道）+ `domain/`（事件 DTO、RunMutex 端口）+ `constants/`（行为基座）
- `llm/` — LLM 接入：`domain/`（消息家族、ModelClient 端口）、`application/`（结构化输出）、`adapters/`（OpenAI 兼容客户端 + wire 漏斗）
- `memory/` — 记忆栈：`application/`（块/消息/会话编排、压缩、整合）、`adapters/`（MySQL 持久化与命名锁）、`domain/`（实体/DTO/schema/端口）
- `intent/` — 意图识别（可选预处理层）：`domain/`（规则、知识库、schema）、`application/`（集成缝）、`adapters/`（Jev 判定客户端）
- `security/` — 安全：`application/`（中间件洋葱 + 命令解析）、`adapters/`（语义判定、Docker 沙箱、审计落库）、`domain/`（DTO）
- `skills/` — Skill 插件体系：`application/`（发现、装配、用户技能物化）、`adapters/`（bio_skill 只读 SQL）
- `rag/` — RAG 检索栈：`application/`（门面、索引器、检索器、分块、BM25）、`adapters/`（向量库、对象存储、编码器、PDF 解析、组件工厂与用户域工厂）、`domain/`（实体/DTO/端口）
- `vision/` — 视觉分析：`application/`（看图编排与纯算法）、`adapters/`（PyMuPDF 管线与视觉客户端构造）、`domain/`（数据模型、几何）
- `tools/` — 工具域（合并包）：`domain/`（Tool ABC、ToolResult 契约）、`application/`（校验、runtime_context、外置、语义根、make_tools 装配）、`adapters/`（具体工具实现 + 大结果对象存储）、`constants/`
- `constants/` — 跨模块领域词汇：`enums/`（风险等级、副作用、来源）+ `derived.py`（派生表）

跨层共享的叶子能力（text/tokenization/frontmatter/atomic）不在这里，统一放 `biopilot/common/`。

## Responsibilities

- 定义并维护运行层的**三层边界**（见 Core Logic）：谁是词汇与契约、谁是编排、谁翻译外部世界。
- 承载全部与模型交互、检索、记忆、安全保障、工具执行有关的实现。
- 保证本层对上层（`api` / `controller` / `service` / `mapper` / `schema`）的出边为 0；可以依赖 `biopilot/common`。

## Core Logic

- **只放子包**，不放裸 `.py` 模块（外加本 manifest 与 `__init__.py`）。散在根下的模块按「服务于谁」收进子包；跨包共享的叶子进 `biopilot/common/`，不要让 engine 兼任 common 层。
- **子包内部按三层分**：`domain/`（本域词汇与契约：实体/DTO/schema/**端口**，零外部依赖；第三方词汇库仅 pydantic/yaml——数据校验与随包知识库解析，无 I/O 无协议，类型词汇用 TYPE_CHECKING 守卫）、`application/`（编排与用例：流程、循环、状态机；**不得构造外部世界适配器**）、`adapters/`（外部世界翻译：模型协议、SQL、对象存储、子进程、HTTP 判定服务）。另有 `config/`（组件行为参数，跟组件走）与 `constants/`（本包词汇）——这两者不属于三层，是正交的参数与词汇载体。新增子包照这套分。
- **适配器判据**：模块 import 外部世界客户端库（`openai` / `httpx` / `pymysql` / `pymilvus` / `minio` / `fitz` / `subprocess`）→ adapters；纯编排与算法 → application；词汇/契约/端口 → domain。本地文件系统、`importlib` 动态加载、ContextVar 不算外部世界（插件发现、技能物化因此归 application）。
- **应用层依赖端口，不依赖适配器实现**：跨「外部世界」的依赖（模型、存储、对象存储、判定服务、互斥锁）在 domain/ 里以 Protocol/ABC 声明端口（`llm/domain/port.py` 的 `ModelClient`、`memory/domain/ports.py`、`agent/domain/ports.py` 的 `RunMutex`、`rag/domain/ports.py`），实现放 adapters，组装根注入。例外白名单（application → adapters 直接 import）：① 目标适配器模块自身无客户端库 import（纯函数翻译，如 `llm/adapters/wire.py`）；② 自有持久化（memory 的 database/message/block/agent_state/named_lock、rag 的 index_state_store——MySQL 是硬依赖自有设施，非可替换外部服务）；③ 各域的构造工厂（`rag/adapters/components.py`、`vision/adapters/builders.py`——组装根在域内的延伸，惰性构造语义的落点）。白名单是唯一豁免清单：新增豁免必须同步更新架构守护测试（tests/core/test_architecture.py）。
- **枚举一枚举一文件**：各子包的 `constants/` 里，枚举放 `enums/<snake_case>.py`，其余常量放同层 `constants.py`；`constants/__init__.py` 只做再导出。判据是「有没有第二个消费方」。
- **两类 `config/`**：顶层 `biopilot/config/` 是设置页（数据库）与环境变量可调的全局参数；子包的 `config/` 放该包**组件自己的行为参数**（调用点各给一套、不进全局配置）。后者不是层间搬运的数据，故不住 `domain/dto/`。
- **`rag` 与 `vision` 必须同层**：rag 的媒体块要向 vision 取图与视觉描述（core 内部的惰性 import），分开摆会让包级依赖成环。
- **`engine` 其余域包不得 import `engine.tools.adapters`**：工具实现是模型的 tool-call 入向适配器，方向恒为 tools → 各域包。tools 的 `domain/` / `constants/`（契约与键名）与 `application/`（加载期校验、runtime_context）是被 agent 消费的契约与运行时协作者，放行——与「agent → tool 契约」的既定方向一致。spawn（tools 内）消费 engine.agent 应用层是合法反向。

## Key Entry Points

- `agent/application/runtime.py` — ReAct 主循环
- `security/application/middleware/base.py` — 安全中间件协议与异常体系
- `rag/application/rag_service.py` — RAG 门面（构造收口见 `rag/adapters/factory.py`）
- `tools/domain/entity/tool.py` — Tool 抽象与安全元数据
- `llm/domain/port.py` — ModelClient 端口

## Usage And Change Notes

- **包根只留子包与 manifest**：判据是「这个单元有没有自成体系的约定」——真正要避免的是为只有一两个内聚模块、没有独立约定的目录单设一份 manifest。
- 新增或搬移模块时先按三层判据定位（domain / application / adapters），再按域选子包；搬完把包内 import 改成具体子模块路径（不可经包 `__init__`，那会成环）。
- 子包之间新增依赖要检查方向：**core 内部允许互相依赖，但对 `api` / `controller` / `service` / `mapper` / `schema` 的出边必须为零**；跨层共享只能依赖 `biopilot/common`。

## Dependencies And Collaboration

- 本层被 `api/`（入口与装配）与 `service/` 依赖；本层不反向依赖它们。
- 子包之间的主要依赖：`agent` → `llm` / `tools`（契约）/ `skills` / `memory` / `security` / `intent`；`rag` → `vision`；`security` → `biopilot/common` 与 `constants`；`intent` 与 `memory` 互相独立。
- 与各 agent 通过 `Tool` 抽象协作（`tools/domain/entity/tool.py`），不是硬编码调用链。

## Investigation Rule

1. 先读本文件确认目标子包与它是否有自己的 manifest。
2. 引擎与工具执行看 `agent/`；模型接入看 `llm/`；记忆看 `memory/`；意图看 `intent/`；安全看 `security/`；检索看 `rag/`；图表看 `vision/`；插件与外部工具看 `skills/`；工具契约与实现看 `tools/`。
3. 共享叶子能力在 `biopilot/common/`，跨模块领域词汇在 `constants/`——排查「同一逻辑有两份实现」时先看这两处。
4. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/core tests/agent tests/tools -q
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/core tests/agent tests/tools -q
conda run -n biopilot python -m pytest tests/core/test_architecture.py -q  # 三层边界守护
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 子包 manifest：[`agent/`](agent/AGENTS.md) / [`llm/`](llm/AGENTS.md) / [`memory/`](memory/AGENTS.md) / [`intent/`](intent/AGENTS.md) / [`rag/`](rag/AGENTS.md) / [`vision/`](vision/AGENTS.md) / [`security/`](security/AGENTS.md) / [`skills/`](skills/AGENTS.md) / [`tools/`](tools/AGENTS.md) / [`constants/`](constants/AGENTS.md)
- 跨层共享基础设施：[`../../common/AGENTS.md`](../../common/AGENTS.md)

## References

- [`agent/application/runtime.py`](agent/application/runtime.py)
- [`agent/application/state.py`](agent/application/state.py)
- [`tools/domain/entity/tool.py`](tools/domain/entity/tool.py)
- [`../../agents/AGENTS.md`](../../agents/AGENTS.md)
