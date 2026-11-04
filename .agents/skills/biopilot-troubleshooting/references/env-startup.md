# env-startup — 服务栈 / conda / Python / 配置

按报错关键词 Ctrl-F 定位。条目按发现顺序追加，不重排。

### `SyntaxError` / `compile()` 报错但代码看起来没问题（Python 3.13 代理字符）
- **根因**：用系统 `python3`（3.13）跑了项目代码；3.13 对含代理字符的 docstring 的 `compile()` 更严格，3.11（项目 env）可通过。
- **修法**：改用 `conda run -n biopilot python …`；脚本内的 shebang/调用链一并检查。
- **验证**：同一命令在 biopilot env 下通过；`conda run -n biopilot python -V` 输出 3.11.x。

### Milvus 容器反复重启 / crash loop（Standalone 崩溃循环）
- **根因**：Docker VM 内存不足（曾默认 1.9G，Milvus Standalone 崩溃循环）。
- **修法**：Docker Desktop 调 VM 内存 ≥4GB 后 `docker compose up -d` 重建；数据卷在 `.biopilot/infra/milvus/` 不用动。
- **验证**：`docker compose ps` 中 milvus 状态 Up 且 9091 健康检查通过，不再重启。

### 批量入库被某一篇 PDF 中断（旧工具名 `index_all`，该工具已退役）
- **根因**：解析是进程内 PyMuPDF（无外部服务，也没有超时这回事），但索引器**没有单篇容错**——逐篇调 `index_document`，其中 `extract_pdf` 对损坏/加密/非 PDF 文件会抛异常并一路穿出去，整批就此停住。
- **修法**：`index_paths(paths=[...])` 逐条回报 indexed/skipped/empty/failed，**不因单篇失败中断**；排查是哪一篇时看它的逐条回报（现役三件：`index_paths` 入库 / `reindex_all` 删除后收敛 / `index_status` 体检）。
- **验证**：`index_paths` 跑完并列出那一篇的 failed 原因；`index_status` 显示其余篇目已入库。

### 某篇 PDF 读不出来 / 取不到标题
- **根因**：解析全在进程内（PyMuPDF），失败只有两类：①文件本身损坏、加密或根本不是 PDF（抛异常，工具层转成错误文本）；②文件正常但**Java 侧标题提取判据不过**——元数据标题被判为垃圾、或首页版面候选全是页眉/水印/作者行。第二类**不报错，只是 `bio_paper.title` 为空**（宁空勿错的设计），表现为检索块缺少标题前缀、引用库拒绝加入。
- **修法**：①损坏/加密的手工确认后换文件；②标题为空时在文件管理页「编辑标题」手动补齐（不要拿文件名顶上），保存后知识库内论文会自动重索引。
- **验证**：`read_pdf` 秒级返回正文或明确错误；文件管理页显示或可编辑标题；索引块的块前缀带上该标题。

### 一个子 agent 承包多篇 PDF 阅读，撞穿子 agent 超时帽（早先版本误记为「并发拖垮依赖栈」）
- **根因**：**任务形状**。一次「读一下某目录下所有论文」实测：supervisor 把整批交给当时的一个 `qa-agent`（该角色已删除，现按域拆成 paper-agent / note-agent），它对该目录 3 篇 PDF 逐个 `read_pdf`。当时的读路径经 `ReadPdfTool → RAGService.parse_pdf_cached`（该缓存函数已不存在——读 PDF 现已与索引栈解耦），那把缓存**解析全程持 `RAGService` 全局锁**，同一批并发发起的多个 `read_pdf` 到这一层会被**串行化**——三篇解析分别约 60.1 / 61.0 / 13.7 秒，墙钟合计约 135 秒，再加一轮 LLM 与工具开销就超过该角色 180 秒的预算（现役同类角色预算：note-agent 900s / paper-agent 420s，见 `config.agents.timeouts`）。
- **别误判成「并发解析压垮了依赖栈」**：那把锁使这些解析并没有真正并发，且 Milvus 同期重启与「读 PDF 的并发」之间没有因果证据（本条早先版本这么写过，已纠正）。
- **修法**：任务侧「同类 N 件 → N 路 spawn，一个对象一个子 agent」——每路各有独立预算，即便底层串行也各自等得起。
- **验证**：单个子 agent 的 `read_pdf` 不连续跑多个不同 path；单篇精读子任务不撞超时帽。

### 对话时报「LLM API key 未配置」
- **根因**：设置页「对话模型」未填密钥，且无环境变量 `BIOPILOT_LLM_API_KEY`；新环境常缺。
- **修法**：在设置页填 `llm.api_key`（加密存 `bio_config_secret`），或写 `.env` 的 `BIOPILOT_LLM_API_KEY`；RAG 的 key 独立配 `rag.embedding.api_key` 或 `BIOPILOT_RAG_EMBEDDING_API_KEY`。
- **验证**：对话不再报 key 错误，正常返回回答。

### 检索只有 BM25 结果 / 稠密路静默消失
- **根因**：`rag.embedding.api_key` 未配——设计为软降级（路由退纯 BM25、检索跳稠密路），只警告不报错。
- **修法**：配置 `rag.embedding.api_key`（或继承检查 `rag.rerank` 段）；重启会话生效。
- **验证**：查询时日志无「RAG 查询编码失败，本次退化为纯 BM25 检索」告警；检索结果含向量召回来源。

### BM25 检索结果缺失或与重启前不一致（重启后漂移）
- **根因**：旧版本重启后 BM25 索引未恢复；已在 `biopilot/engine/rag/services/retriever.py`（BM25 进程级裸 rebuild，自向量库重建）修复。命中此症状说明代码是旧版本。
- **修法**：更新到含裸 rebuild 的版本；临时绕过可触发一次任意查询（首查即重建）。
- **验证**：重启后首次查询结果与重启前一致；`retriever.py` 中存在 rebuild 恢复逻辑。

### 改了设置页/配置文件里的一个字段，程序行为完全没变（无报错、静默不生效）
- **根因**：①优先级固定为「默认值 < `bio_config` < `config.yaml` 引导层 < 环境变量」，设置页对 `source=env` 的字段只读，env 会压过数据库；②数据库覆盖有 5 秒进程内缓存，另一个进程的修改不是瞬间可见；③`rag.*` 与 `platform.search_timeout/transfer_timeout` 被进程级单例捕获，页面标「需重启」；④迁移后 `config.yaml` 里的运行时字段不再参与加载，只认引导层。
- **修法**：在设置页确认该字段的 `source` 徽标与「需重启」标记；env 字段改 `.env`/compose 后重启；数据库字段保存后丢弃 Agent 缓存，下一轮生效；RAG 配置改完重启 webapi。
- **验证**：`biopilot config export` 看有效配置；`conda run -n biopilot python -c "from biopilot.config import BioPilotConfig; print(BioPilotConfig.from_env().<改动字段路径>)"` 与页面一致。

### 重负载任务跑到一半 Milvus 崩溃循环（`streaming node is not alive` / `Slow etcd operation` / `session is expired`）
- **根因**：与上一条同源但触发条件不同——不是 VM 一开始就太小，而是**任务把 VM 内存吃穿**。Docker VM 约 3.9GB，其中 Milvus 栈（etcd + minio + standalone）并发检索/写入时能占 1GB+。实测一次「读一下某目录下所有论文」：Milvus 在 13 分钟内重启 9 次（此前累计 RestartCount 25），随后整个 OrbStack VM 也重启一次（表现为**所有**容器同时变成 `Up N seconds`，RestartCount 清零）。VM 内内存耗尽后 Milvus 的 datanode/mixcoord/streamingnode 拿不到 etcd 租约（日志依次出现 `etcdserver: request timed out, waiting for the applied index took too long`、`Slow etcd operation`、`streaming node is not alive`、`confirm the lease is expired`）→ standalone 进程退出，`restart: unless-stopped` 反复拉起。宿主同为内存紧张时（`sysctl vm.swapusage` 显示 swap 用量高、宿主 load average 远超核数）会加剧。
- **因果的成色**：重启时间窗与该次重负载窗重合、机制（重负载把 VM 内存吃穿）也说得通，但**未经受控实验验证**——别在别的场合把它当成已证结论照搬。
- **修法**：两条腿——① **削负载**：重活别堆在一轮里做完（多篇大 PDF 分轮、同类任务拆多路 spawn）；PDF 解析已是进程内的事，不再占 VM 资源，但**建索引**要调云端嵌入并写 Milvus，仍是重活。② **加资源**：调大 OrbStack/Docker VM 内存；宿主侧先释放内存（关掉大内存 IDE 等）比调 VM 更立竿见影。
- **验证**：重负载任务跑完后 `docker inspect milvus-standalone --format '{{.RestartCount}}'` 不再增长；`curl -s localhost:9091/healthz` 持续返回 OK；`docker ps` 各容器 uptime 连续不归零。

### Milvus 半死时单次 `rag_retrieve` 阻塞 25~90 秒（`Connection recovery failed` / `Fail connecting to server on localhost:19530` / `DEADLINE_EXCEEDED`）
- **根因**：Milvus 端口仍开着但服务已半死（或正在重启）时，检索不是立刻失败而是长时间阻塞——`biopilot/engine/rag/storage/vector_store.py` 构造 `MilvusClient(uri=uri)` **未传 timeout**，全部 RPC 也无 timeout，于是走 pymilvus 默认值：`retry_on_rpc_failure`（`retry_times=75`、backoff 上限 3s）与 `connection_manager._recover → reconnect`（connect deadline 被规范化为 10s）。而一次 `Retriever.retrieve()` 要做**多次** Milvus RPC（首次 `all_documents()` 重建 BM25 + 每个改写 query 一次 `query` + 至多两次 `fetch_by_ids`），几个 10s 恢复等待累加即 25s/64s/90s 量级。**下面这些「没有超时、没有熔断」的断言说的是当时那个版本**——当时 `RAGService.milvus_available()` 结果永久缓存且无人调用（现已是带 TTL 的可连性探测，并被 `IndexStatus` 消费）。
- **放大伤害**：子 agent 超时帽是预算制（当时 qa-agent 默认 180s——该角色已删除；现役同类角色 note-agent 900s / paper-agent 420s，见 `biopilot/config/schemas/sections.py` 与 `config.agents.timeouts`），1~2 次阻塞检索就能吃穿整个预算 → 子 agent `timeout` → supervisor 重派仍超时 → 整轮十几分钟拿不到结果，最后只能转成向用户请示（旧的 `ask_user` 工具已删除——现在是把问题写进最终回答）。
- **附注**：Milvus 不可用时 `rag_retrieve` **不会**软降级成纯 BM25，而是返回固定文本「⚠️ 向量检索不可用（Milvus 异常）」（`biopilot/tools/rag/rag_retrieve.py`）；`Retriever` 里只有 embedding 与 reranker 两路有 try/except，向量路与 BM25 路的 `fetch_by_ids` 均无保护——BM25 索引虽在本地内存，其元数据仍依赖 Milvus，所以「退纯 BM25」在 Milvus 挂掉时物理上不可行。别把这条与「embedding 未配 key → 退纯 BM25」的软降级混淆。
- **修法（已实施）**：各 RPC 传 `rag.storage.timeout`（读路径 5s / 写路径 60s），并在 `rag_retrieve` 边界加检索侧熔断器（`biopilot/engine/rag/services/breaker.py`，冷却 60s，跳闸期间直接返回降级文本）。旧版本上遇到时先升到含 `RetrievalBreaker` 的版本。
- **验证**：`docker stop milvus-standalone` 后调一次 `rag_retrieve`，应在数秒内返回降级文本，而不是阻塞数十秒；再调一次应瞬时返回（熔断短路）；Milvus 起来后过冷却窗口自动恢复，无需重启进程。

### `biopilot` 启动即 `ImportError: cannot import name ... from 'biopilot.api'`
- **根因**：包门面（`biopilot/api/__init__.py`）的 `__all__` 漏再导出某个符号（如 `WebConfig`）——CLI 与测试可能从 `biopilot.api.app` 直连绕过门面，测试全绿也挡不住门面缺角。
- **修法**：把缺的符号加进门面的 import 与 `__all__`；新增公开符号时同步维护门面。
- **验证**：`conda run -n biopilot python -c "from biopilot.api import <缺失符号>"`。

### 适配层起不来：`memory_dsn 必须是 mysql://... 形式` / 启动即 fail-fast（`BIOPILOT_MEMORY_MYSQL_DSN`）
- **根因**：`runtime.memory_dsn` 的规范来源是 `BIOPILOT_MEMORY_MYSQL_DSN`（`BIOPILOT_RUNTIME_MEMORY_DSN` 优先）；两者都没有时回落代码默认值 `mysql://root@127.0.0.1:3307/biopilot`。配置库、标题更新、论文/文档端点的共享 `MemoryDB()` 都依赖它。
- **修法**：启动命令带上 `BIOPILOT_MEMORY_MYSQL_DSN="mysql://root@127.0.0.1:3307/biopilot"`；库不存在时先 `docker compose up -d`（MySQL 容器首启由 `docker/mysql-init/` 建库建表；数据卷已存在的旧容器**不会**重跑 init，表缺失要手动执行 `server/script/sql/` 与建表脚本）。
- **验证**：`docker exec biopilot-mysql mysql -uroot biopilot -e "SHOW TABLES;"` 列出 bio_memory_block/bio_message/sys_user 等表；适配层 `/health` 返回 ok。旧数据卷升级时先执行 `server/script/sql/migrations/2026-11-02-rename-tables.sql`。

### 服务端启动报 `Access denied for user 'root'@'<网桥 IP>' (using password: YES)`
- **根因**：SpringBoot 的 datasource 口令与容器 MySQL 不一致。容器按 `MYSQL_ALLOW_EMPTY_PASSWORD` 建库，root 是**空密码**；`application.yaml` 里若写了本机自装 MySQL 的密码，容器实例一旦接管端口就失败——客户端带密码、服务端空密码，MySQL 只回 `using password: YES`。宿主经 Docker 端口映射连接时，服务端看到的来源是网桥网关 IP（如 `192.168.97.1`）而非 `localhost`，别被这个 IP 带偏成授权问题（`root@'%'` 本来就在）。
- **修法**：`application.yaml` 的口令留空，或经 `SPRING_DATASOURCE_PASSWORD` 给值；宿主 3306 被本机 MySQL 占用时容器实例发布到 3307，端口与 `start.sh` 共用 `BIOPILOT_MYSQL_PORT`。
- **验证**：`mysql -h127.0.0.1 -P3307 -uroot --skip-password` 能连；启动日志出现 `Started BioPilotApplication`。

### 网页端带 body 的请求（对话/上传）到适配层全变空体，FastAPI 报 `Field required`（Java→Python 代理）
- **根因**：SpringBoot 代理用的 java.net.http.HttpClient 默认带 h2c 升级头（`Upgrade: h2c` + `HTTP2-Settings`），uvicorn 把它当协议升级请求处理并**吞掉请求体**——GET 不带体所以列表类接口正常，极有迷惑性。
- **修法**：`AgentProxyController` 的 HttpClient 已锁 `HttpClient.Version.HTTP_1_1`；新增代理端点必须共用这个 client，别 new 默认的。
- **验证**：`curl -F "file=@/tmp/x.pdf" -H "satoken: <token>" http://127.0.0.1:8080/api/v1/papers` 返回 `{"status":"ok",...}` 而非 422。

### 管理端/profile 之类接口返回 500「系统繁忙」，日志里却没有异常堆栈
- **根因**：全局异常兜底把未知异常转成通用文案且不打日志（设计如此，防泄内部细节）；「不存在的路径」也曾被它吞成 500（现 NoResourceFound 已如实 404）。
- **修法**：先核对请求路径与方法是否真的存在（看控制器注解）；确实存在再本地复现并临时在兜底 handler 加日志定位。前端调错路径现在会拿到 404 + `接口不存在: <path>`。
- **验证**：`curl -i http://127.0.0.1:8080/auth/profile`（无 token 应 401；拼错路径应 404）。

### `mvn spring-boot:run -pl bio-admin -am` 报 `Unable to find a suitable main class`
- **根因**：`spring-boot:run` 这类直接目标调用会在 reactor **每个**模块上执行，`-am` 把 bio-common-core 等库模块拉进来，它们没有 main class。
- **修法**：先 `cd server && mvn install -DskipTests` 一次，之后 `cd server/bio-admin && mvn spring-boot:run`（reactor 里只有启动模块自己）。
- **验证**：启动日志出现 `Started BioPilotApplication`，`curl http://127.0.0.1:8080/auth/profile` 返回 401（而非连接拒绝）。

### 某个不常用的端点/分支一调就 `NameError: name 'X' is not defined`（导入期一切正常）
- **根因**：未定义名藏在冷路径里（ rarely 执行的端点、异常分支、闭包），导入与常规测试都覆盖不到；典型如缺模块级 `logger`、`from pathlib import Path` 只导入了 `pathlib`、闭包引用 `except X as e` 的隐删变量、内层函数引用兄弟函数的局部变量。
- **修法**：`/opt/miniconda3/envs/biopilot/bin/python -m pyflakes biopilot/` 全量扫 `undefined name`（F821），逐条修；修完保持扫描清零作为回归线。except 变量在闭包里用要提前 `req = e` 绑定。
- **验证**：pyflakes 对 `biopilot/` 输出 0 条 undefined name；对应端点 curl 200。
