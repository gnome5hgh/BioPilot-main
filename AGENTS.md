# AGENTS.md

本文件为 AI 编码代理（ZCode / Claude Code / Codex 等）提供 `BioPilot` 仓库的进入方式、阅读路径与必须遵守的规则。

**本文件只写规则，不写现状快照**：字段表、文件清单、枚举取值、当前数量都以源码为准，抄一份到这里必然过期，而读到的旧快照比读不到更糟。判据是「删掉它，agent 会不会做错事」——不会、但得去源码翻的，就删掉。唯一保留的非规则是**导航**（目录地图与「去哪里找」的指针）。

## Scope

- 本文件是 `BioPilot` 根工作区的总 manifest，负责建立仓库边界、阅读路径、治理规则与公共约束。
- 作用范围覆盖整个仓库；进入更深层目录后，服从该目录更近的 `AGENTS.md`。
- **子 manifest 不会自动注入**：客户端只注入从当前目录向上找到的**第一份** manifest，不逐层合并。所以**改某个模块之前，按 Routing 主动读它那份**——那里面是必须遵守的约定，不是可读可不读的背景。
- 事实优先级：源码与测试 > 本 manifest 及各级子 manifest > `docs/` 设计文档。文档与代码冲突时以代码为准。

## 模块定位

- 名称：`BioPilot`
- 路径：`.`
- 角色：`repo-root-workspace-manifest`
- 当前定位：**实验室私有部署的多用户生信科研 Agent 平台**。三层结构：`web/`（Vue3 前端）→ `server/`（SpringBoot：鉴权/角色/审计 + 平台业务 + 引擎接入）→ `biopilot/`（Python 引擎：原单机多 agent 研究助手，经 FastAPI 适配层暴露 HTTP/SSE）。学生登录使用；数据按 `user_id` 行级隔离（MySQL）与 `users/<uid>/` 前缀隔离（OSS/Milvus collection）。
- 引擎本体不变的部分：单根 agent（supervisor）接收每一轮用户输入 → 可选的意图预处理 → ReAct 循环 → 拆解子任务派发子 agent → 聚合各子 agent 的结构化摘要后汇总回答。
- 绑定环境：Python 3.11 / conda env `biopilot`；Java 21 + Maven（`server/`）；Node ≥ 20（`web/`）。

## 目录结构

```text
BioPilot/
├─ web/                # 前端（Vue3 + Vite + TS 风格 JS）：登录/对话/文件/文献/知识库/引用库/终端面板/管理
├─ server/             # SpringBoot 3（Java 21）：bio-admin(启动装配) bio-modules(业务域+引擎接入) bio-common(通用件)
├─ biopilot/           # Python 引擎：webapi/(入口+HTTP/SSE 适配层) config/(参数)
│                      #   common/(跨层基础) core/(agent 运行层) tools/(工具)
├─ agents/             # Agent 插件：AGENT.md（契约）+ tools.py
├─ .biopilot/         # 静态资产 intent/ + 服务卷 infra/ + 启动日志/pid run/（运行数据根默认在此，可重定向）
├─ .agents/skills/     # 给编码代理按需加载的 skill（与本仓运行时无关）
├─ docs/               # 设计文档：adr/ learning/ research/
├─ .scratch/           # 开发过程文档：spec/ticket（matt-pocock 本地约定，gitignored；历史 spec/plan 归档在 .scratch/archive/）
├─ tests/              # 测试套件
├─ scripts/            # 实验与标定脚本
├─ .env.example        # 部署引导模板（连接串/外部地址/本机路径）；运行时配置在数据库
├─ config.yaml         # 可选、gitignored：只剩部署引导；首次启动会把旧的运行时配置导入数据库
├─ docker-compose.yml  # 依赖服务栈（Milvus Standalone + MinIO + MySQL）
├─ docker/mysql-init/  # MySQL 容器首启建库脚本（biopilot/biopilot_test + sys_* 表）
└─ AGENTS.md
```

### 当前目录分层含义

- 三层调用链：`web/`（5173，Vite 原样代理 `/api` → 8080）→ `server/`（8080，Sa-Token 鉴权 + 业务表 + 引擎接入）→ `biopilot/webapi/`（8300，SSE 对话与数据端点）→ 引擎本体。`server/` 与 `biopilot/` 之间是**信任边界**：内网头 `X-User-Id` 即真相，适配层不二次鉴权、只绑回环/内网。
- `biopilot/` 是引擎主包；`webapi/` 是进程入口与 HTTP/SSE 适配层（`entry.py` 入口、`assembly.py` 会话装配），`config/` 是参数唯一声明点，`common/` 是跨层共享基础设施（常量/纯函数/原子写/通用对象存储），`core/` 是 agent 系统技术核心（`rag/` 与 `vision/` 已住进 `core/` 内）。平台数据访问（论文/文件/文档）已迁 Java `bio-file`。
- `server/` 按 SpringBoot + cde-common 惯例分三块：`bio-admin`（只放启动类、配置与健康检查，纯装配）、`bio-modules`（按业务域拆分的模块，外加技术适配层 bio-gateway；域清单以目录为准）、`bio-common`（跨域共享的基础设施模块，按单一关注点拆分）。
- 浏览器接口统一挂在 `/api/v1/**`（管理端 `/api/v1/admin/**`），`/internal/**` 是 Java↔Python 的跨栈契约、不版本化；**URL 按资源命名，不跟模块名走**——模块拆分/改名不牵动前端路由。
- `agents/` 是 Agent 插件目录，每个子目录一个角色；它的 `description` 会被自动收进运行时的可派发清单。
- `.biopilot/` 是静态资产与数据卷根：`intent/` 入库，`infra/` 是 docker 数据卷，`run/` 是本地启动脚本的 pid 与日志（不入库），`user-cache/` 是按用户隔离的派生缓存（附件副本、技能物化，不入库）。运行期数据默认也落在这里，但可用 `runtime.workspace` / `BIOPILOT_RUNTIME_WORKSPACE` 重定向到仓库外；用户缓存根由 `runtime.user_cache_dir` 单独控制。
- `.agents/skills/` 是给编码代理用的技能，与 BioPilot 运行时的用户技能是**两条不相干的线**。
- `docs/`、`scripts/`、`tests/` 不入库是既定策略；运行期目录与个人路径不得入库。

## 技术结构

- 语言与运行时：Python ≥ 3.11（引擎与适配层，依赖在 `pyproject.toml`）；Java 21 + SpringBoot 3.5（`server/`，MyBatis-Plus + Sa-Token）；Vue3 + Vite（`web/`）。
- 依赖服务栈：Milvus Standalone（向量库，gRPC 19530 / 健康检查 9091）+ MinIO（图表原图与论文原文的对象存储，回环 9000）+ MySQL 8.4（记忆/会话/业务真相源，回环 3307），由仓库根 `docker-compose.yml` 一次拉起，数据落 `.biopilot/infra/`。
- 外部模型端点：对话 LLM、视觉模型、RAG 嵌入与精排都是 OpenAI 兼容的 HTTP 接口，端点、模型名与 key 经配置提供，不硬编码。
- 可调参数与默认值的唯一声明点是 `biopilot/config/schemas/sections.py`；运行时配置的真相源是 MySQL 的 `bio_config`（设置页写稀疏覆盖），`config.yaml` 只保留启动引导项，环境变量优先级最高。SpringBoot 侧配置在 `server/bio-admin/src/main/resources/application.yaml`。

## 环境与依赖

- 两类 API key 都必须由用户提供：LLM（`llm.api_key` / `BIOPILOT_LLM_API_KEY`）、RAG 嵌入与精排（`rag.embedding.api_key` / `BIOPILOT_RAG_EMBEDDING_API_KEY`）。可在设置页填写（加密存 `bio_config_secret`），也可走环境变量。LLM key 留空即启动 fail-fast；RAG key 留空不崩，但检索退纯 BM25、索引明确报错、图表视觉描述不可用。
- `corpus.analysis_dir` / `corpus.research_dir` 这类**个人路径没有默认值、必须显式配**（留空则回落到 `<workspace>/analysis` / `<workspace>/research`）。用户给不出就如实说，不要猜、不要填占位值、不要静默跳过。笔记与论文**不落本地语料目录**：笔记定稿进文档编辑器，论文由平台 OSS + `bio_file`（paper 行）提供。
- 检索栈（Milvus/MinIO）是**软依赖**：不可达只警告降级、不阻塞启动；记忆库 MySQL 与 LLM key 是**硬依赖**：不可达/未配置即启动 fail-fast（真相源不能静默降级）。单测连 compose 的 biopilot-mysql（`biopilot_test` 库）；`scripts/rag/rag_eval/` 的评测要连 Standalone 与 MinIO。

## 仓库职责

- 承载一个可运行的多用户科研 Agent 平台：注册/登录/鉴权/角色（两档）/审计（SpringBoot），对话编排、领域子 agent、RAG 检索、引用管理、记忆系统、终端面板（宿主 shell，可选开启），文件管理（论文/数据文件/文档）/文献搜索/知识库/设置（三层协作）。
- 维护 agent 插件契约、工具的安全元数据与安全中间件链。
- 维护设计文档体系：按模块划分的 ADR（正文恒为最新设计）与学习材料。
- 承载编码代理的协作资产：各级 manifest、`.agents/skills/`、`.biopilot/intent/`。

## 核心协作逻辑

- **没有确定性 pipeline**：路由、工具选择、任务拆解全由 LLM 的 ReAct 循环驱动；工具只是喂给模型的 JSON Schema 定义。
- **编排归 supervisor**：它按各子 agent 的 `description` 选型，顺序与并行由它自主决定。契约里写的「一个对象一路」是提示层的编排期望，不是闸门。
- **意图只作信号**：意图识别是可选预处理层，产出一条类别信号注入根 agent 的 head，不参与任何决策（约束见下方硬红线）。
- **领域产物各自归口**：长期记忆由轮末后台整合独占写、所有 agent 只读（`memory_read`）；语料索引归 `rag-agent` 独占读写，其余角色需要时派发它；引用库是平台功能（Java），agent 不读写。
- 会话跨轮靠 SQL 落盘 + `session_id` 一致；`docs/`、`scripts/`、`tests/` 不入库，**文档漂移不会被 git 顶出来**，改完要主动核对。

## Python 与 Java 的职责边界

三层平台的分工不是「按语言分」，而是「按职责分」。新增代码前先回答：它属于平台业务，还是 agent 运行时？

- **Java（`server/`）拥有平台业务**：注册/登录/登出、Sa-Token 会话、角色（ADMIN/USER）、用户与登录日志、项目管理、文件目录（论文/数据文件/文档/分析产物的 HTTP CRUD 与 OSS 生命周期）、论文索引状态机（`KbStateService`）、知识库状态概览与论文清单（`bio_file` 的 paper 行统计）、论文标题/书目提取（`bio-common-pdf`）、引用库（`bio-citation`：勾选、维护、导出 `.bib`）、定时任务管理与调度、文献搜索与导入、MCP 检索源配置（`bio-common-mcp` 通用客户端）、外部 URL 抓取（`bio-common-net`：公网校验 + 重定向逐跳校验，PDF 下载与文献导入共用）、管理端查询（用户/会话/审计读取）、用户技能管理（`bio-skill`：标准包准入、OSS 包、启停/更新/卸载）。
- **Python（`biopilot/`）拥有 agent 运行时**：ReAct 编排、LLM 接入、记忆与压缩、RAG 索引/检索/分块、视觉、安全中间件与确认、终端 PTY、对话 SSE/确认/上下文用量、知识库试检索/分块读取/运行时信息、引擎配置（`bio_config` + 引导 env）、用户技能运行时消费（按用户物化技能缓存）。
- **端点落点判据**：只写平台表、不读引擎进程内状态、不参与引擎领域产物写路径 → Java；需要读 agent 缓存/确认 future/窗口用量，或需要调用 RAG/记忆 → Python。跨边界写一律走 `/internal/*`（`X-Internal-Token` + `X-User-Id`）：平台表（含 `bio_file` 的索引状态列）只有 Java 写，引擎经 `/internal/kb/*` 上报状态；引擎需要文件字节时调 `/internal/attachments/*`，不直连 OSS。
- **单写者规则（按表/列）**：
  - `bio_agent_state`、`bio_message`、`bio_memory_block`、`bio_memory_block_history`、`bio_memory_consolidation_cursor`、`bio_security_audit_event`：Python 写，Java 只读（项目删除时清 `project_id` 是唯一例外）。
  - `bio_rag_index_state`：Python 独占（RAG 增量索引状态）。隔离键是 `user_domain`（`local` 或登录用户 id），不是 `user_id`——本地语料域没有用户归属，这是该表不带 `user_id` 列的唯一理由。
  - `bio_config`、`bio_config_secret`、`bio_config_history`：Python 独占（运行时配置、加密密钥、保存历史）；Java 只经 `/admin/settings` 代理，不直连这三张表。
  - `bio_file`：Java 独占（论文/数据文件/文档/分析产物统一表）。按列分写者：`bio-file` 写身份/文件/书目/`citation_id`/`kb_enabled`，`bio-kb` 写 `indexed/index_status/index_error/indexed_at/chunk_count`。Python 只读身份/勾选/状态列，**不直接 INSERT/UPDATE/DELETE**——索引结果经 `/internal/kb/{indexing,result}` 上报，强制重建经 `/internal/kb/requeue-all` 复位。文件正文只在 OSS，表里只有 `oss_key`/`sha256`/`version`；同名唯一键是 `(user_id, name_key)`，artifact 的 `name_key` 为 NULL（不占名）。
  - `bio_citation`：Java 独占（引用库行）；Python 不读写。
  - `bio_oss_gc`：OSS 删除 outbox（系统级、无 `user_id`；Java 定时任务读写）。
  - `bio_schedule_task`：Java 独占（任务定义与 `last_run_at` / `next_run_at` 进度列都由 Java 写）；Python 只接收 `/internal/schedule/run` 触发后执行 agent。
  - `bio_skill`：Java 独占写（用户技能安装记录，带 `user_id`）；Python 只读 `enabled/content_sha`，用于把技能包物化成本地缓存。
  - `sys_*`、`bio_project`、`bio_literature_mcp_server`：Java 独占。
- **表命名规范**：系统表 `sys_<entity>`；BioPilot 业务表 `bio_<domain>_<entity>`，域内用单数实体名（如 `bio_file`、`bio_schedule_task`）。平台表 DDL 只在 `server/script/sql/` 与 `docker/mysql-init/` 维护；Python 的 `_SCHEMA` 只建引擎自己的表。
- **禁止事项**：Java 不实现 agent 编排/记忆/检索/切块/嵌入；Python 不新增平台 CRUD（新增前先判断是否属于 agent 运行时），不自建文献检索/MCP 客户端/调度循环/外部 URL 抓取，也不直连 OSS 取平台文件——检索调 `/internal/literature/search`、PDF 下载调 `/internal/literature/fetch-pdf`（SSRF 与 `%PDF` 校验在 Java `bio-common-net`）、文件字节调 `/internal/attachments/*`、产物登记调 `/internal/files/artifacts`、定时任务只接收 `/internal/schedule/run`；Web 不直连 8300，全部经 `/api` → Java。

## 硬红线

以下是不分模块、任何地方都必须成立的不变式。违反它们通常不报错，只会让功能静默失效或让设计倒退。

- **错误一律降级为文本**：工具与中间件的错误转成 `ToolResult` 文本回传模型，由模型决定重试或调整。唯一向上抛的异常是 `MaxTurnsExceeded`。
- **截断必须续写，绝不交付残缺内容**：模型因长度被截断时，把半截内容与续写提示放回 in-context 继续循环，不能把那半截当最终回答返回。
- **安全只有策略轴，执行类工具必须进程外隔离**：进程内决定「要不要用户点头」。代码与命令执行只经 `run_python` / `run_shell` 的一次性 Docker 容器（断网/只读挂载/根只读）；要新增能执行 shell 或任意代码的工具，必须先有等强度的进程外隔离，否则不做。
- **网页终端不属于 agent 工具面**：它是用户显式打开的宿主 shell，由 `runtime.allow_host_shell` 控制（默认关），子进程只带环境白名单；不得包装成工具交给模型，也不得在共享部署默认开启。终端面板按 `user_id` 复用一条会话，关闭/切换只脱离不杀进程。
- **只有一个确认决策点**：策略引擎合并全部升级因后统一弹一次确认；其余中间件只登记升级原因。硬拒只来自显式规则，不来自档位。
- **所有拦截走同一条降级通道**：拒绝、确认失败、安全阻断都表现为带 `decision` 的 `ToolResult`，绝不绕过 ReAct 循环。
- **写工具必须声明安全元数据**（`risk_level` / `side_effects` / `provenance` 等），注册表加载时校验合法值。
- **路径检查与写盘共用同一份解析结果**：检查通过的路径参数就地归一化为解析后的绝对路径（防 TOCTOU）。
- **SQL 是唯一真相源**：压缩与窗口驱逐**永不删 SQL 行**；读—改—写类块写入必须经一次持锁事务，不能「读旧值→算新值→写回」分三步做。
- **知识库一致性以 `bio_file` 的 paper 行为唯一真相**：引擎启动与每轮索引都对账向量库——不属于任何「已加入」论文的块直接清理，已就绪论文的向量块数与 `chunk_count` 不一致则重建；`failed` 不自动重试（用户重试由 Java 先置 `queued`），避免对账反复消耗解析与嵌入资源。
- **压缩只改窗口，旧摘要并入重摘**：每次压缩把上一份摘要作为底稿送回摘要模型（Claude Code 式，集成指令约束漂移），窗口恒只有一份最新摘要、多次压缩不累积；摘要不携带用户原话（业界无代码插全量原话的先例，实测还会挤爆摘要预算）——硬约束、截止时间等边界由任务快照逐字保留（快照从不参与重摘），原话不作回溯；摘要失败时保持原窗口，不拿空摘要替换历史。
- **摘要不携带用户原话与工具引用**：压缩摘要有损、用户原话不进摘要且不作回溯；跨会话知识只走记忆块（`bio_memory_block`）。工具结果外置后的指针只在窗口内可回取。
- **领域产物的读写各自归口**：长期记忆写入归轮末后台整合（`MemoryConsolidator`），**不向任何 agent 暴露记忆写工具**；所有 agent 只通过只读召回（`memory_read` / `read_tool_result`）读取。语料索引归 `rag-agent` 独占读写。引用库是平台功能（Java `bio-citation`），agent 既不读写也不做溯源标注。supervisor 因此持有 spawn + 只读召回，仍不持有执行类工具。
- **`allowed_spawns` 与风险档位由框架强制**，不靠提示词自律；批量同类对象**一个对象一路**派发。
- **技能的读写各自归口**：管理面（`bio_skill` 表、OSS `users/<uid>/skills/`、安装准入）归 Java `bio-skill`；引擎只做只读消费（按 `content_sha` 物化的用户缓存），不写管理状态，也不接受 `tools.py` 这类「加载即执行」的非标准扩展。**内置流程（笔记/选题/审查）不是 skill**，写在对应 agent 的 `AGENT.md` 里，模板在该角色 `references/` 下。
- **意图只作信号**：不决定派发顺序、不作派发门禁、不持跨轮状态；spawn 对意图零引用，子 agent 不做意图识别。
- **`user_id` 即隔离键，信任边界不二次鉴权**：SpringBoot 内网调用携带的 `X-User-Id` 即真相，Python 适配层只验「头存在与否」（fail-closed）、不做鉴权，物理前提是适配层只绑回环/内网。引擎侧所有领域表（`bio_memory_block`/`bio_message`/`bio_file`/`bio_agent_state`/`bio_security_audit_event`/`bio_memory_consolidation_cursor`）都带 `user_id`；例外有三类：`bio_rag_index_state` 的隔离键叫 `user_domain`（`local` 或用户 id），因为本地语料域不属于任何用户；`bio_config`/`bio_config_secret`/`bio_config_history` 是部署级全局配置，没有用户维度；`bio_oss_gc` 是系统级 outbox，没有用户维度。SpringBoot 业务表的行级 `user_id` 过滤由 MyBatis-Plus 租户插件统一注入（`sys_*`/`bio_agent_state`/`bio_security_audit_event` 豁免），**不许手写 where 补过滤**。
- **跨进程互斥只认 MySQL 锁**：per-conversation run 互斥与整合消费权认领都走 DB 锁（`GET_LOCK`/行级 `FOR UPDATE`），进程内锁只作单进程快路径；拿不到锁降级为文本提示，绝不排队阻塞。
- **OSS 一致性方向固定**：对象先落、元数据行后写（失败留孤儿对象、不留死行）；删除反向（先删行、再删对象，孤儿可后台对账清扫）。论文标题恒来自解析器出口，上传登记也不回退文件名。
- **config 快照语义**：run 启动时对配置做一次快照、全程读快照；设置页与模型切换都是**下一个 run 生效**，绝不热改在途 run。保存设置会丢弃 Agent 缓存；`rag.*` 与平台客户端是进程级单例，标「需重启」。
- **SSE 契约**：`done` 帧恒发（含异常路径），客户端断开映射为取消 run（不留悬挂任务占会话锁）；确认等待由策略引擎计时（300 秒自动拒绝），不依赖连接存活。
- **审计落 MySQL**：`bio_security_audit_event` 表是审计真相源（不是 JSONL 文件）；审计行不参与租户插件过滤。
- **同一会话的身份链四处一致**：web 会话 id → SpringBoot（`X-User-Id`/`X-Conversation-Id` 头透传）→ AgentManager → `Agent.session_id`，错位会让各自读到空数据；子 agent 共享父 `session_id`，各自持有独立 `conversation_id`（消息不互相污染窗口）。
- **多用户 RAG 隔离**：向量 collection 按用户域加后缀（`_{user_domain}`），`local` 域保持原名；BM25 按用户分语料，重建走 singleflight。
- **流式零开销**：`stream_callback` / `telemetry_callback` 为 `None` 时，全链路保持非流式行为。
- **常量与配置的落点**：一个枚举一个文件（`constants/enums/<name>.py`，`__init__` 只再导出）；常量**有第二个消费方才**进 `constants/`；可调参数进顶层 `biopilot/config/`，组件自己的行为参数跟组件走。
- **标题宁空勿错且只由 Java 产出**：论文标题由 `bio-common-pdf` 在入库时提取并写 `bio_file.title`；Python（RAG 索引、`read_pdf`）只从数据库读标题，不再自行推导。取不到就如实为空，**绝不回退到 PDF 文件名**。
- **已退役的实现不要复活**：意图的旧混合路由与澄清链路、路径白名单、记忆的 markdown 投影与 git 投影提交、`conversation_search` 召回工具都已整体移出主干。跨会话知识只走记忆块（`bio_memory_block`），会话内精确回溯不再提供（摘要有损、原话不留）。旧文档里的描述不作论据。

## 关键入口

- 仓库规则与阅读路径：`AGENTS.md`
- 进程入口与装配根：`biopilot/webapi/entry.py`（入口）、`biopilot/webapi/assembly.py`（Web 会话对象图）
- Web 适配层（agent 运行时 API：SSE/确认/知识库/终端/内部调用）：`biopilot/webapi/app.py`（规则见 [`biopilot/webapi/AGENTS.md`](biopilot/webapi/AGENTS.md)）
- SpringBoot 启动类：`server/bio-admin/src/main/java/com/biopilot/admin/`；引擎接入（代理/SSE/终端 WS）：`server/bio-modules/bio-gateway/`
- 前端入口与路由：`web/src/main.js`、`web/src/router/`
- 参数声明点：`biopilot/config/schemas/sections.py`
- 配置模板与字段示例：`.env.example`（引导层）；可调字段以设置页/`biopilot/config/services/schema.py` 为准
- Agent 插件契约：`agents/AGENTS.md` 与各 `agents/<name>/AGENT.md`
- 设计文档索引：`docs/adr/`（设计为什么这么做）与 `docs/learning/`（实现怎么运作）

## 渐进式阅读路径

- 仓库边界与公共规则：先读本文件。
- 改主包某模块：`biopilot/AGENTS.md` → 对应子包 `AGENTS.md` → 源码与 `tests/`。
- 改某个 agent 的契约：`agents/AGENTS.md` → `agents/<name>/AGENT.md` → `tools.py`。
- 改用户技能运行时：`biopilot/core/skills/AGENTS.md`；改内置流程：对应 `agents/<name>/AGENT.md` 与 `references/`。
- 追设计背景：`docs/adr/`（按模块一份，正文恒为最新）→ 需要历史时 `docs/adr/修正记录.md`。
- 想知道某块实现**怎么运作**（而不是为什么这么设计）：`docs/learning/`（按主题一份，正文同样恒为最新）。
- 排查异常：先过 `.agents/skills/biopilot-troubleshooting/SKILL.md` 的已知根因表。

## 调查规则

1. 先读本文件建立边界，再按 Routing 读目标模块那份子 manifest，最后才读源码。
2. 设计背景查 `docs/adr/`；历史决策查 `docs/adr/修正记录.md`。
3. manifest 不够用时深入源码、`pyproject.toml` 与调用链核实。**代码事实优先于任何文档概括**。
4. 实验与标定事实查 `scripts/<模块>/` 下各实验目录的 `results/` 报告（`scripts/` 不入库，删掉不可恢复）；评测题集在 `goldens/`、产物在 `results/`。
5. 运行期目录（`.biopilot/` 下非入库子目录、`.venv/`、`__pycache__/`）与 gitignored 产物不作事实源，除非明确要求排查运行时现象。

## 常用命令

```bash
# 安装开发依赖（conda env 内）
conda run -n biopilot pip install -e ".[dev]"

# 全量测试（Python）
conda run -n biopilot python -m pytest tests/ -v

# 单个测试
conda run -n biopilot python -m pytest tests/agent/test_agent.py::TestExecTool -v

# 依赖服务栈（Milvus Standalone + MinIO + MySQL）；./start.sh 会先拉起，此命令用于手动管理
docker compose up -d

# Web 平台一键启动（容器 + 适配层 + SpringBoot + 前端，含就绪探测与日志跟随）
./start.sh        # 停止：./stop.sh（容器与数据保留）；前端 http://localhost:5173

# 部署形态（实验室服务器）：容器化整套平台（nginx:80 + server + webapi）
docker compose --profile full up -d --build   # 只起基建则省略 --profile full

# 配置运维（运行时配置在 MySQL；旧 config.yaml 首次启动会自动导入）
biopilot config import config.yaml    # 手动导入（默认把文件改写成只含引导层）
biopilot config export                # 导出有效配置（不含密钥）
biopilot config history               # 查看保存历史
biopilot config rollback <version>    # 回滚到历史版本

# 服务端测试（bio-admin）
cd server && mvn test -pl bio-admin
```

- 依赖服务由 `./start.sh` 或 `docker compose` 负责拉起；引擎进程本身不再自动探测/拉起容器。
- 非交互命令（测试 / 脚本 / 安装）**一律经 `conda run -n biopilot`**，不要用裸 `python` 或 `pip`。
- Python 适配层与引擎都通过 `BIOPILOT_MEMORY_MYSQL_DSN`（或显式的 `BIOPILOT_RUNTIME_MEMORY_DSN`）拿 DSN：标题更新、论文/文档端点的轻量 SQL 以及配置库本身都依赖它，启动时务必带上。

## 统一编码规范

- 注释面向所有人——包括新人和非维护者。用中文写，不出现内部项目代号（任务/决策/评审编号、日期、spec/ADR 章节引用），也不写过程流水账；需要背景时用一句白话说明。
- 每个函数/方法的 docstring 至少说明其**作用**；关键算法思路、非显而易见的边界条件（安全/并发/失败处理）是重点。非显而易见的逻辑保留 WHY，但用通俗语言，不写成变更日志。
- **docstring 按 Google 风格写**（三个双引号；首行一句话摘要并以句号收尾，与正文之间空一行）：有参数写 `Args:` 并**逐个**列出，有返回值写 `Returns:`（只返回 `None` 可省），会抛异常写 `Raises:`，生成器用 `Yields:`。函数名与签名本身已说清、且 docstring 只有一句话时，这些段落可以**整段**省略——要么不写、要么列全，不挑「显而易见之外的」写。仓库无 linter 配置，此条靠人工遵守。
- 按逻辑块组织注释：同一逻辑块的多行代码合并成一条块注释，放在块首；避免每行一注。每条注释紧跟其描述的代码。

```python
# BAD:  "Loop over items and add to result"        ← 复述代码
# GOOD: "遍历所有 items 并去重,因为多源搜索结果可能包含同一篇论文的不同版本"
```

- 修改代码时同步更新注释——过期注释比没有注释更糟。
- **复用优先**：新增前先检索既有实现，禁止平行造轮子；扩展既有能力优先于新增本地实现。

## 文档维护规则

- **本文件与各级子 manifest 只写规则，不写容易失效的静态计数、一次性状态或临时结论**（详见文首判据）；需要现状就读源码或 ADR / learning。**新增或整理 manifest 时加载 [`agents-md-governance`](.agents/skills/agents-md-governance/SKILL.md)**——判据、根/单元骨架模板、体检清单与装载行为实测都在那份 skill 里。
- **改代码后先自问要不要同步设计文档**：接口签名、行为语义、结构或已记录决策发生变化都算。需要同步时**先让测试通过再改文档**——先让代码行为被测试锁住，再让文档描述现状。
- **ADR（`docs/adr/`）**：
  - 按模块划分，**一份 ADR = 一个模块**（清单见该目录，文件名即模块）。新决策扩展对应模块那份；确属新模块才新建，编号顺延。
  - **正文恒为最新设计**：设计变更直接改写正文对应小节，不在正文留「修正说明 / 修正（日期）」这类历史痕迹，也不写「原方案被废弃」。
  - **修正史统一追加进 `docs/adr/修正记录.md`**（日期 / 文档 / 变更摘要 / 来源）——ADR 与 learning 共用这一份。
  - 跨模块变更**按归属拆分**写进各模块 ADR，不设跨模块 ADR；每个 ADR 要显式声明它与相邻模块的分工边界。
  - **编号不回收、空缺须补齐**：删除或合并 ADR 后重编号，并同步更新所有活文档的引用。历史 spec/plan 里的旧编号不回改。
  - 文中互相引用只写「见 ADR XXXX」。
- **learning（`docs/learning/`）与 ADR 同一套规则**——它与 ADR 只差读者：ADR 讲「为什么这么设计」，learning 讲「实现怎么运作」，**同步义务完全一样**。
  - 按主题划分，**一份文件 = 一个主题**（清单见该目录，文件名即主题）。新主题才新建，编号顺延。
  - **正文恒为最新**：行为或结构变了直接改写正文对应小节，**不追加「更新（日期）」节、不在正文留修正痕迹**；历史上已追加的「更新」节要折回正文。
  - **修正史同样追加进 `docs/adr/修正记录.md`**（同一份文件，标注是 learning 的哪一篇）。不要另起一份 learning 修正记录。
  - **编号不回收、空缺须补齐**：删除或合并后重编号，并同步更新所有活文档的引用；历史文档里的旧编号不回改。
  - 文中引用只写指针（如「见 learning 04」）。
- spec（`.scratch/<feature>/spec.md`）是**实施期文档**（本地 tracker 约定见 `docs/agents/issue-tracker.md`；历史 spec/plan 在 `.scratch/archive/`）：实现过程中发现它与最终代码不一致，或当前改动影响上层接口，都要回修。
- **`docs/`、`scripts/`、`tests/` 都不入库**，所以文档漂移不会被 diff 顶出来，也没有 CI 替你拦：改完要主动核对受影响的文档。

## Routing

- 当前目录是 `BioPilot` 根工作区 manifest。
- 前端入口：[`web/AGENTS.md`](web/AGENTS.md)
- 服务端入口：[`server/AGENTS.md`](server/AGENTS.md)
- 引擎主包入口：[`biopilot/AGENTS.md`](biopilot/AGENTS.md)（其下 [`config/`](biopilot/config/AGENTS.md) / [`core/`](biopilot/core/AGENTS.md) / [`tools/`](biopilot/tools/AGENTS.md) / [`webapi/`](biopilot/webapi/AGENTS.md)；`core/` 之下的子 manifest 见 core manifest）
- 插件目录入口：[`agents/AGENTS.md`](agents/AGENTS.md)
- 资产与数据根入口：[`.biopilot/AGENTS.md`](.biopilot/AGENTS.md)（其下 [`intent/`](.biopilot/intent/AGENTS.md)）
- 设计文档索引：[`docs/adr/`](docs/adr/)（修正史：[`docs/adr/修正记录.md`](docs/adr/修正记录.md)）、[`docs/learning/`](docs/learning/)
- 排障技能：[`.agents/skills/biopilot-troubleshooting/SKILL.md`](.agents/skills/biopilot-troubleshooting/SKILL.md)
- manifest 治理技能（搭建 / 增删模块 / 体检）：[`.agents/skills/agents-md-governance/SKILL.md`](.agents/skills/agents-md-governance/SKILL.md)

## References

- [`README.md`](README.md)
- [`.env.example`](.env.example)（部署引导模板）
- [`REVIEW.md`](REVIEW.md)（代码审查的仓库定制层：重点盯防区域 / 输出约束 / 风险分流，供 cross-review 等审查流程读取）
- [`web/AGENTS.md`](web/AGENTS.md)
- [`server/AGENTS.md`](server/AGENTS.md)
- [`docker-compose.yml`](docker-compose.yml)
- [`pyproject.toml`](pyproject.toml)
- [`biopilot/AGENTS.md`](biopilot/AGENTS.md)
- [`agents/AGENTS.md`](agents/AGENTS.md)
- [`.biopilot/AGENTS.md`](.biopilot/AGENTS.md)
- [`docs/adr/`](docs/adr/)（按模块的设计决策；修正史：[`docs/adr/修正记录.md`](docs/adr/修正记录.md)）
- [`docs/learning/`](docs/learning/)（按主题的实现讲解，与 ADR 同一套同步规则）
- [`.agents/skills/biopilot-troubleshooting/SKILL.md`](.agents/skills/biopilot-troubleshooting/SKILL.md)
