# BioPilot

实验室私有部署的多用户生信科研 Agent 平台：网页端登录使用，围绕「读论文 → 做笔记 → 追问题」的科研工作流，提供多 Agent 协作、RAG 知识库检索、引用管理与记忆系统；数据按用户隔离（MySQL 行级 + OSS 前缀 + 独立向量 collection）。

## 功能特性

- **多 Agent 协作**：supervisor 单根调度，读子 agent 能力清单（`<available_agents>`）按需拆解子任务并派发（paper-agent 文献检索与阅读 / review-agent 审稿评阅 / note-agent 论文笔记 / research-agent 选题与研究计划 / rag-agent 平台论文检索与索引体检 / bio-agent 沙箱代码执行与数据分析），各子 agent 返回结构化摘要后聚合回答
- **意图识别（可选预处理层，默认关）**：规则层高精度模式命中即定类，不命中交给结合对话史的判定服务，产出一条单类别信号注入根 agent；它只作信号，不决定派发顺序
- **RAG 检索栈**：本地版面解析 PDF（PyMuPDF 还原章节与坐标，不依赖外部服务）→ 学术分块（按节切 + 句界滑窗，丢弃参考文献/样板章节残渣）→ Milvus 向量 + BM25 混合检索 → RRF 融合 → 云端重排
- **引用库**：平台侧的文献条目集合（从文件管理勾选论文/手工维护），支持 author-year / GB/T 7714 复制与 `.bib` 导出；不参与 agent 溯源
- **视觉分析**：PDF 图表区域检测与提取，原图入 MinIO 对象存储，多模态模型看图解读
- **记忆系统**：对话持久化 + 分层记忆块 + 后台 debounce 记忆整合 + 会话历史与上下文用量
- **Skills 机制**：用户技能按 `user_id` 隔离（`bio_skill` 表 + OSS `users/<uid>/skills/`）；内置流程已并入各 agent 的 `AGENT.md`
- **文献检索**：平台内置 Europe PMC + 管理员在设置页配置的 MCP 检索源；前端文献页与 agent 共用 Java 侧聚合结果

## 环境要求

| 依赖 | 说明 |
|---|---|
| Python ≥ 3.11 | 运行环境，建议用虚拟环境（venv / conda）隔离 |
| Docker + Docker Compose | 依赖服务栈：Milvus Standalone 向量库 + etcd + MinIO 对象存储，由仓库根的 `docker-compose.yml` 一次拉起。向量检索与图表原图存储都跑在这套服务上 |
| paper-search-mcp | 由 `docker compose` 的 `paper-search-mcp` 服务提供，Java MCP 客户端连接；无需宿主机装 uv |
| LLM 端点 | 一个 OpenAI 兼容且支持工具调用的对话端点（base_url + api_key）。图表看图复用同一端点 |
| 嵌入 / 精排端点 | 一个 OpenAI 兼容的嵌入与重排端点（默认硅基流动 `Qwen/Qwen3-Embedding-0.6B` + `Qwen/Qwen3-Reranker-0.6B`）。RAG 稠密检索与重排都用它 |

## 快速开始

```bash
# 1. 安装（建议在虚拟环境 / conda env 中）
pip install -e ".[dev]"

# 2. 部署引导：复制模板并填入 LLM 与嵌入/精排的 api_key
cp .env.example .env
# 运行时配置（模型参数/检索/安全档位等）在网页「设置」里维护，落 MySQL

# 3. 启动依赖服务（Milvus + etcd + MinIO）并等健康
docker compose up -d
curl http://localhost:9091/healthz   # → OK

# 4. 启动全套平台（适配层 + SpringBoot + 前端）
./start.sh
```

浏览器打开 `http://localhost:5173` 注册使用。

`docker/*.Dockerfile` 默认用阿里云镜像装 apt 包与 PyPI 依赖（直连官方源在国内常见只有几十 kB/s）。人在海外或想换别的源，用同名环境变量覆盖后重建：

```bash
PIP_INDEX_URL=https://pypi.org/simple APT_MIRROR=deb.debian.org docker compose build
```

### 网页平台启动

```bash
docker compose up -d                       # MySQL + MinIO + Milvus（首启自动建库建表）

# ① Python 适配层（8300；DSN 环境变量必带）
BIOPILOT_MEMORY_MYSQL_DSN="mysql://root@127.0.0.1:3307/biopilot" biopilot

# ② SpringBoot（8080；首次先 cd server && mvn install -DskipTests）
cd server/bio-admin && mvn spring-boot:run

# ③ 前端（5173）
cd web && npm install && npm run dev
```

浏览器打开 `http://localhost:5173` 注册使用；第一个管理员需要手工提权：
`docker exec biopilot-mysql mysql -uroot biopilot -e "UPDATE sys_user SET role='ADMIN' WHERE user_name='你的用户名';"`，然后重新登录。

### 一键安装提示词

把下面整段提示词复制给你的 AI 编码工具（ZCode / Claude Code / Codex 等），它会照着在当前仓库里把环境装好并验证：

```text
请帮我在本机把 BioPilot 的开发环境装好并验证通过。仓库就是当前工作目录。

要求：只做环境安装与配置，不要改任何源码。

步骤：
1. 先读仓库根的 AGENTS.md，按其中的 Commands 与环境要求执行。
2. 创建并激活一个 Python ≥ 3.11 的虚拟环境，然后安装：pip install -e ".[dev]"
3. 复制部署引导模板：cp .env.example .env
4. 向我要下面两个 API key 并写进 .env，拿到之前不要填假值、不要跳过：
   - BIOPILOT_LLM_API_KEY：OpenAI 兼容的对话端点 key（默认端点 https://api.deepseek.com/v1）
   - BIOPILOT_RAG_EMBEDDING_API_KEY：OpenAI 兼容的嵌入/精排端点 key（默认 https://api.siliconflow.cn/v1）
5. 启动依赖服务栈并等它真的健康：
   docker compose up -d
   然后轮询 curl http://localhost:9091/healthz 直到返回 OK（首次会拉镜像，可能几分钟）。
6. 产物目录不需要配置：笔记定稿进网页文档编辑器，论文由平台 OSS 提供；分析与研究产物默认落在 .biopilot 工作区。
7. 验证：
   - python -m pytest tests/ -q（单测用 Milvus Lite 内嵌，不依赖服务栈）
   - 启动 ./start.sh，确认适配层 / 服务端 / 前端均就绪
8. 每一步做完向我汇报。任何一步失败，把原始报错贴给我并说明你的修复方案，不要静默跳过或降级处理。
```

## 配置说明

所有可调参数的默认值唯一声明在 `biopilot/config/sections.py`（dataclass 字段默认值）。**运行时配置的真相源是 MySQL 的 `bio_config`**，管理员在网页「设置」里修改；`.env` / 环境变量只承载进程启动前必须知道的引导项（MySQL/Milvus/MinIO 地址、内部 token、本机目录、配置加密密钥），且优先级最高。本地首次启动会把旧的 `config.yaml` 自动导入数据库，之后只剩引导层（可迁移到 `.env` 后删除）；容器部署没有旧文件可导入，直接用 compose 的环境变量。

新增配置项不需要改前端：设置页按 `biopilot/config/schema.py` 的字段描述自动渲染。主要配置段：

| 配置段 | 用途 |
|---|---|
| `llm` | 主 LLM：端点 / key / 模型 / 上下文窗口 |
| `vision` | 多模态视觉模型（图表看图分析） |
| `rag.embedding` | 云端嵌入 + 重排端点与模型 |
| `rag.storage` / `rag.store_images` | Milvus 连接与图表原图的对象存储（MinIO） |
| `rag.retriever` / `rag.chunker` / `rag.query_rewrite` | 检索参数 / 分块参数 / 查询改写 |
| `intent` | 意图识别子层（默认关；开启需 Vercel AI Gateway 的网关 key） |
| `corpus` | 笔记 / PDF / 研究产物的根目录路径 |
| `agents.timeouts` | 子 agent 超时覆盖表（仅 YAML 可配） |
| `platform` | Java 平台后端地址与内部 token（agent 调 `/internal/*` 用） |

API key 也可经环境变量提供（如 `BIOPILOT_LLM_API_KEY`、`BIOPILOT_RAG_EMBEDDING_API_KEY`、`BIOPILOT_VISION_API_KEY`）。

## 架构概览

```
web/             前端（Vue3 + Vite）:登录 / 对话 / 文件 / 文献 / 知识库 / 引用库 / 终端面板 / 管理
server/          SpringBoot 3.5（Java 21）:注册登录鉴权 / 业务表 / 内网代理（bio-admin
                 / bio-modules / bio-common 三模块）
biopilot/
  main.py        启动类:配置子命令 + uvicorn
  api/           FastAPI 装配层:create_app / deps / router / lifespan / 异常映射
  controller/    路由层:chat / session / settings / model / terminal / kb / internal
  service/       应用服务:ABC 接口 + impl（SSE、附件、设置、知识库索引、删户、调度）
  mapper/        SQL 访问层
  schema/        HTTP 请求/响应 Pydantic 模型
  domain/        WebConfig / WebSession / RuntimeState / TerminalSocket
  config/        全局可调参数的唯一声明点
  engine/        agent 运行时:agent(ReAct 循环) / llm(客户端 + 结构化输出)
                 / intent(意图识别) / memory(记忆系统) / security(安全中间件)
                 / skills(Skill 注册表) / tool(Tool 抽象)
                 / rag(RAG 检索栈:解析 → 分块 → 索引 → 混合检索 → 重排)
                 / vision(视觉分析:图表检测 + 提取 + 多模态解读)
  tools/         面向 agent 的工具集:文件 / 记忆 / RAG / 搜索等（装配工厂在 services/assembly.py）

agents/          各角色 agent 的 AGENT.md + tools.py（插件目录，位于仓库根）
.biopilot/      运行时数据根与资产目录:skills(流程 skill) / intent(意图知识库) / infra(服务数据卷)
```

数据流：用户输入 →（可选）意图识别 → supervisor ReAct 循环（必要时 spawn 子 agent）→ 工具调用（本地工具；文献检索经 SpringBoot 内部端点）→ 结构化摘要聚合 → 流式回答。网页端的调用链：浏览器 → SpringBoot（鉴权 + `X-User-Id` 归属头）→ 适配层（SSE 帧契约）→ 引擎。

## AI 协作入口

仓库根的 `AGENTS.md` 是面向所有 AI 编码代理（ZCode / Claude Code / Codex 等）的治理 manifest——只写**规则**（该怎么做、什么不许做、去哪里找），不写字段表、文件清单这类会被代码改活的现状快照。`web/`、`server/`、`biopilot/` 及其 `config/`、`engine/`（再往下十二份）、`tools/`、`api/`，以及 `agents/`、`.biopilot/`（再往下 `skills/`、`intent/`）各有一份子 manifest 写就地约定。注意：客户端只**自动注入其中一份**（从当前目录向上找到的第一份），所以改某个模块前要按 AGENTS.md 的 Routing 主动读它那份。`CLAUDE.md` 是 Claude Code 的入口薄指针（本地维护、不入库）。事实优先级：源码与测试 > AGENTS.md 及各级子 manifest > `docs/` 设计文档。
