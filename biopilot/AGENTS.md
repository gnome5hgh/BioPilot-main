# biopilot

## Scope

- 覆盖 `biopilot/` 主包。`api/`、`service/`、`controller/`、`domain/`、`mapper/`、`schema/`、`config/`、`engine/`、`tools/` 与各子包各有自己的 manifest（见 Routing）；**改对应模块前先读它那份**。
- 根 manifest 的硬红线在本层同样成立，这里不重复。

## Module Positioning

- 角色：`package-root-manifest`
- 职责：主包唯一入口。`biopilot.main` 是进程启动类，`biopilot.api.app.create_app` 是 FastAPI 应用工厂，`biopilot.service.impl.assembly_service_impl` 是 Web 会话装配实现。
- 定位：**只承载 agent 运行时与引擎领域状态**；平台业务 CRUD 归 Java（`server/`）。分工与单写者规则以根 `AGENTS.md` 的「Python 与 Java 的职责边界」为准。

## Directory Structure

```text
biopilot/
├─ main.py        # 启动类：config 子命令分发 + uvicorn
├─ api/           # FastAPI 装配：app/deps/router/lifespan/exception_handlers（有 manifest）
├─ controller/    # 路由层：一个 controller 一个 APIRouter（有 manifest）
├─ service/       # 应用服务：ABC 接口 + impl/（有 manifest）
├─ mapper/        # SQL 访问：service 只经这里读写引擎领域表（有 manifest）
├─ schema/        # HTTP 契约：请求/响应 Pydantic 模型（有 manifest）
├─ domain/        # 应用层 dataclass / Protocol（有 manifest）
├─ config/        # 全局可调参数（有 manifest）
├─ common/        # 跨层共享基础设施（有 manifest）
├─ engine/        # agent 系统技术核心，内含 rag/ vision/（有 manifest）
└─ tools/         # 面向 LLM 的工具声明与装配（有 manifest）
```

- `main.py` 是唯一允许留在包根的代码模块；其余关注点必须落进上述子包。
- `__init__.py` 负责包标记（含 gRPC 环境守卫），`__main__.py` 是 `python -m biopilot` 的结构性入口。

## Layering

- 依赖方向：`api → controller → service → mapper → common/engine/tools`。
- `engine/` 与 `tools/` 不得 import `api/`、`controller/`、`service/`、`mapper/`、`schema/`；这是「某组件该不该搬进 engine」的硬依据。
- `controller/` 只做参数解析、`Depends` 注入、调用 service、返回响应；不写 SQL、不装配 Agent。
- `service/` 每个服务一个 `abc.ABC` 接口，实现放 `service/impl/`；跨模块共享的进程级状态在 `service/state.py`，每个 FastAPI 应用实例的状态在 `domain/runtime_state.py`。
- `mapper/` 只放 SQL；service 不写裸 SQL。
- `schema/` 只放 HTTP 请求/响应模型；engine 各模块自己的领域 schema（`engine/memory/schemas/`、`engine/intent/schemas/`、`engine/rag/domain/{dto,entity}/` 等）原地保留，不向顶层集中。

## Responsibilities

- 提供进程入口、FastAPI 应用工厂与服务容器（`main.py` / `api/` / `service/container.py`）。
- 定义全局可调参数及其加载优先级（`config/`）。
- 承载全部运行层能力（`engine/`）与它们的对外工具；引用库、论文标题提取、文献检索（含 MCP 客户端）归 Java，不在本包实现。
- `common/` 只放跨层纯能力；平台数据访问归 Java `bio-file`，不再设 Python 数据适配层。
- 通过包门面暴露重量组件，不让外部深入组件内部结构。
- **保留 agent 运行时 API**：对话 SSE/确认/上下文用量、知识库试检索/分块读取/运行时信息、终端、`/internal/kb/{sync,runtime}`、`/internal/schedule/run` 与用户数据清理。知识库状态统计与论文清单归 Java；论文/文件/文档/定时任务/文献搜索的平台 CRUD 不在本包新增。
- **数据所有权**：`bio_agent_state`、`bio_message`、`bio_memory_block`、`bio_memory_block_history`、`bio_memory_consolidation_cursor`、`bio_security_audit_event`、`bio_rag_paper_status`（论文索引状态唯一落点）由本包写；**`bio_file` 的身份/勾选/标题列由 Java 写**，本包只读（勾选变更经 `/internal/kb/sync` 唤醒、可携带重排论文 id，文件字节经 `/internal/attachments/*` 取回）；`bio_schedule_task` 由 Java 写，本包只经内部端点触发。

## Core Logic

- **包根只留 `__init__.py`、`__main__.py` 与启动类 `main.py`**（`__init__.py` 含一处必须在任何 gRPC 导入之前执行的 `GRPC_VERBOSITY` 守卫）；其余关注点落进子包，子包 `__init__` 只做再导出。
- **对外经包门面**：RAG 经 `get_rag_service()`。
- **懒加载单例**：重量组件用双重检查加锁的模块级单例，包导入期不拉重型依赖。新增重量组件照这个形状做。
- **配置快照语义**：run 启动时对配置做一次快照、全程读快照；设置页与模型切换都是下一个 run 生效，不热改在途 run。

## Key Entry Points

- `main.py` — 启动类（配置子命令或启动 Web 适配层）
- `api/app.py` — `create_app()` 工厂与 `run_server()`
- `api/deps.py` — `X-User-Id` / `X-Internal-Token` 校验与服务容器依赖
- `api/router.py` — 汇总全部 controller 的 `APIRouter`
- `api/lifespan.py` — 启动/停服后台任务
- `service/container.py` — 服务容器装配
- `service/impl/assembly_service_impl.py` — Web 会话对象图装配
- `config/sections.py` — 参数与默认值
- `engine/agent/services/runtime.py` — ReAct 主循环

## Usage And Change Notes

- **新增服务**：先写 `service/<name>_service.py` 的 ABC，再写 `service/impl/<name>_service_impl.py`，在 `service/container.py` 装配，最后由 controller 通过 `Depends(get_services)` 取用。
- **新增端点**：先判断能力是否属于 agent 运行时；属于则在 `controller/` 加路由、在 `schema/` 加请求/响应模型，不在 `api/app.py` 里堆处理器。
- **改内部模块名要同步 `tests/` 里的 monkeypatch 字符串目标**：pytest 按「查找处」解析，指错模块不报错，只会让假件静默失效。
- **manifest 与它覆盖的单元同层**：同层有代码模块不影响能不能放 manifest——判据是「这个单元有没有自成体系的约定」。
- 新增重量组件照「懒加载单例」的形状做，不要在导入期构造。

## Dependencies And Collaboration

- `api/` 是入口与装配层，依赖 `controller/`、`service/`、`config/`、`engine/`、`tools/`；被依赖方不反向 import `api/`。
- `controller/` 依赖 `service/` 与 `schema/`；不直接依赖 `engine/`。
- `service/` 依赖 `mapper/`、`domain/`、`config/`、`engine/`、`tools/`。
- `engine/` 依赖 `tools/` 的抽象（`Tool` / `ToolResult`）但不反向；`tools/` 是被消费方。

## Investigation Rule

1. 先读本文件建立主包边界，再按目标模块进对应子包 manifest。
2. 启动或装配异常先查 `main.py`（入口）、`api/app.py`（工厂）与 `service/container.py`（对象图），再往 engine 里找。
3. 参数问题查 `config/`：唯一声明点是 `sections.py`，字段契约在 `schema.py`，存储与加密在 `store.py`；部署引导模板是仓库根 `.env.example`。
4. **改内部模块名要同步 `tests/` 里的 monkeypatch 字符串目标**：pytest 按「查找处」解析，指错模块不报错，只会让假件静默失效；`from X import f` 之后要 patch 的是**导入方**的全局名。
5. 文档与代码冲突时，以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/api tests/core -q   # 装配与配置相关
conda run -n biopilot python -m pytest tests/ -q                     # 全量套件
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/api tests/core -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 直接子包：[`api/`](api/AGENTS.md) / [`service/`](service/AGENTS.md) / [`controller/`](controller/AGENTS.md) / [`domain/`](domain/AGENTS.md) / [`mapper/`](mapper/AGENTS.md) / [`schema/`](schema/AGENTS.md) / [`config/`](config/AGENTS.md) / [`engine/`](engine/AGENTS.md) / [`tools/`](tools/AGENTS.md) / [`common/`](common/AGENTS.md)
- `engine/` 之下：[`agent/`](engine/agent/AGENTS.md) / [`llm/`](engine/llm/AGENTS.md) / [`memory/`](engine/memory/AGENTS.md) / [`intent/`](engine/intent/AGENTS.md) / [`rag/`](engine/rag/AGENTS.md) / [`vision/`](engine/vision/AGENTS.md) / [`security/`](engine/security/AGENTS.md) / [`skills/`](engine/skills/AGENTS.md) / [`tool/`](engine/tool/AGENTS.md) / [`constants/`](engine/constants/AGENTS.md)

## References

- [`main.py`](main.py)
- [`api/app.py`](api/app.py)
- [`service/container.py`](service/container.py)
- [`service/impl/assembly_service_impl.py`](service/impl/assembly_service_impl.py)
- [`config/sections.py`](config/sections.py)
- [`config/settings.py`](config/settings.py)
- [`config/schema.py`](config/schema.py)
- [`config/store.py`](config/store.py)
- [`../.env.example`](../.env.example)
