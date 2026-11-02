# biopilot

## Scope

- 覆盖 `biopilot/` 主包。`cli/`、`config/` 与各子包各有自己的 manifest（见 Routing）；**改对应模块前先读它那份**。
- 根 manifest 的硬红线在本层同样成立，这里不重复。

## Module Positioning

- 角色：`package-root-manifest`
- 职责：主包唯一入口。`biopilot.cli` 是装配根，把配置、安全中间件链、记忆服务、意图层、Agent 装配与 REPL 串成一个进程。
- 定位：**只承载 agent 运行时与引擎领域状态**；平台业务 CRUD 归 Java（`server/`）。分工与单写者规则以根 `AGENTS.md` 的「Python 与 Java 的职责边界」为准。

## Directory Structure

- `cli/` — 装配根：启动预检 + 对象图组装 + 工具装配（有 manifest）
- `config/` — 全局可调参数：默认值的声明点 + 三级加载（有 manifest）
- `common/` — 跨层共享基础设施：常量/通用工具/原子写/出站平台客户端（不是 agent 核心，也不是业务层）
- `core/` — agent 系统技术核心，内含 `rag/` 与 `vision/`（有 manifest，其下各子包各有）
- `tools/` — 面向 LLM 的工具声明，按域分包（有 manifest）
- `terminal/` — 终端交互隔离层（有 manifest）
- `__init__.py` / `__main__.py` — 包标记与 `python -m` 的结构性入口

## Responsibilities

- 提供进程入口与装配根（`cli/`）。
- 定义全局可调参数及其加载优先级（`config/`）。
- 承载全部运行层能力（`core/`）与它们的对外工具、终端交互；引用库、论文标题提取、文献检索（含 MCP 客户端）归 Java，不在本包实现。
- `common/` 只放跨层纯能力；平台数据访问归 Java `bio-file`，不再设 Python 数据适配层。
- 通过包门面暴露重量组件，不让外部深入组件内部结构。
- **保留 agent 运行时 API**：对话 SSE/确认/上下文用量、知识库试检索/分块读取/运行时信息、终端、`/internal/kb/{sync,runtime}`、`/internal/schedule/run` 与用户数据清理。知识库状态统计与论文清单归 Java；论文/文件/文档/定时任务/文献搜索的平台 CRUD 不在本包新增。
- **数据所有权**：`bio_agent_state`、`bio_message`、`bio_memory_block`、`bio_memory_block_history`、`bio_memory_consolidation_cursor`、`bio_security_audit_event` 由本包写；**`bio_paper` 全部列由 Java 写**，本包只读（状态经 `/internal/kb/{normalize,indexing,result}` 上报，文件字节经 `/internal/attachments/*` 取回）；`bio_document`、`bio_file_upload`、`bio_schedule_task` 由 Java 写，本包只经内部端点转发/触发。

## Core Logic

- **包根只留 `__init__.py`**（`biopilot/` 另有 `__main__.py`，`python -m` 的结构性入口）；每个关注点落进子包，子包 `__init__` 只做再导出。
- **对外经包门面**：RAG 经 `get_rag_service()`。
- **懒加载单例**：重量组件用双重检查加锁的模块级单例，包导入期不拉重型依赖。新增重量组件照这个形状做。
- **依赖方向**：`core` 不 import 上层模块（`tools` / `terminal`）——这是「某组件该不该搬进 core」那类判断的硬依据；`rag` 与 `vision` 已在 `core/` 内，core 内部互相依赖是允许的。

## Key Entry Points

- `__main__.py` — `python -m biopilot` 的结构性入口
- `cli/services/assembly.py` — 装配组合根（装配顺序即依赖方向）
- `config/schemas/sections.py` — 参数与默认值
- `core/agent/services/runtime.py` — ReAct 主循环

## Usage And Change Notes

- **包根只留 `__init__.py` 与 manifest**：模块按角色收进子包（`cli/services/`、`config/schemas/`、`core/agent/services/`、`core/tool/domain/`、`common/core/utils/` 都是这么落的），**全仓已无包根裸模块**。新增模块先选子包再落文件；包内 import 一律指向具体子模块路径（不可经包 `__init__`，那会成环）。
- **manifest 与它覆盖的单元同层**：同层有代码模块不影响能不能放 manifest——判据是「这个单元有没有自成体系的约定」，真正要避免的是为只有一两个内聚模块、没有独立约定的目录单设一份。
- **改任何子包的内部模块名，都要同步 `tests/` 里的 monkeypatch 字符串目标**（见调查规则第 4 条）。
- 新增重量组件照「懒加载单例」的形状做，不要在导入期构造。

## Dependencies And Collaboration

- `cli/` 是装配层，依赖 `config/`、`core/`、`tools/`、`terminal/`；被依赖方不反向 import `cli/`。
- `core/` 依赖 `tools/` 的抽象（`Tool` / `ToolResult`）但不反向；`tools/` 与 `terminal/` 是被消费方。

## Investigation Rule

1. 先读本文件建立主包边界，再按目标模块进对应子包 manifest。
2. 启动或装配异常先查 `cli/services/bootstrap.py`（预检）与 `cli/services/assembly.py`（对象图），再往 core 里找。
3. 参数问题查 `config/`：唯一声明点是 `sections.py`，模板与示例是仓库根 `config.example.yaml`。
4. **改内部模块名要同步 `tests/` 里的 monkeypatch 字符串目标**：pytest 按「查找处」解析，指错模块不报错，只会让假件静默失效；`from X import f` 之后要 patch 的是**导入方**的全局名。
5. 文档与代码冲突时，以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/cli tests/core -q   # 装配与配置相关
conda run -n biopilot python -m pytest tests/ -q                 # 全量套件
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/cli tests/core -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 直接子包：[`cli/`](cli/AGENTS.md) / [`config/`](config/AGENTS.md) / [`core/`](core/AGENTS.md) / [`tools/`](tools/AGENTS.md) / [`terminal/`](terminal/AGENTS.md)
- `core/` 之下：[`agent/`](core/agent/AGENTS.md) / [`llm/`](core/llm/AGENTS.md) / [`memory/`](core/memory/AGENTS.md) / [`intent/`](core/intent/AGENTS.md) / [`rag/`](core/rag/AGENTS.md) / [`vision/`](core/vision/AGENTS.md) / [`security/`](core/security/AGENTS.md) / [`skills/`](core/skills/AGENTS.md) / [`tool/`](core/tool/AGENTS.md) / [`constants/`](core/constants/AGENTS.md)
- 跨层共享基础设施：[`common/`](common/AGENTS.md)

## References

- [`cli/services/assembly.py`](cli/services/assembly.py)
- [`cli/services/bootstrap.py`](cli/services/bootstrap.py)
- [`config/schemas/sections.py`](config/schemas/sections.py)
- [`config/services/loader.py`](config/services/loader.py)
- [`../config.example.yaml`](../config.example.yaml)
