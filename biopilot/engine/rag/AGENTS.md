# biopilot/engine/rag

## Scope

- 覆盖 `engine/rag/`：PDF 解析 → 分块 → 向量与 BM25 索引 → 混合检索 → 重排。
- 对外出口是 `tools/rag/` 里那几个工具，只装配给 `rag-agent`。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：维护学术语料的检索栈——把 PDF 变成可检索的块，并对外提供带重排的混合检索。

## Directory Structure

```text
rag/
├─ domain/       # entity/（检索块、章节）+ dto/（解析产物、索引结果、改写结果）
├─ constants/    # 块 id 规则与块类型词（被分块/索引/存储共同消费的契约）
├─ services/     # rag_service.py（门面）+ indexer.py + retriever.py + query_rewriter.py
├─ parsers/      # pdf_extract.py（PDF → 带版面的文本）+ chunker.py + table.py（表格重建）
├─ encoders/     # bm25.py（稀疏）+ embedder.py（稠密）+ reranker.py（精排）
└─ storage/      # vector_store.py（Milvus）+ image_store.py（图表原图）+ index_state_store.py（索引状态）
```

## Responsibilities

- 本地版面解析 PDF，按节切块并丢弃残渣，产出带页码与坐标的块。
- 把块写进向量库与 BM25 索引（两者用同一份带前缀文本），并维护索引状态（MySQL，每用户域一行）。
- 对外提供混合检索：稀疏 + 稠密融合后精排，返回有序块。

## Core Logic

- **领域模型收 `domain/`**：跨层共享的数据模型是各层的公共词汇，只依赖 `constants/` 的取值、不依赖服务实现——消费方一律从 `biopilot.engine.rag.domain` 导入，模型不散落在产出它的实现文件里。
- **RAGService 是唯一门面**：indexer 与 retriever 是同一实例的两个视图、共享一把锁，所以增量写入对查询立即可见。外部只经门面访问，不直连内部组件。
- **唯一文档来源是平台论文**：登录用户域由平台适配层取回 PDF 字节直接索引（**不落盘**），文档标识是 `paper:<paper_id>`、指纹是内容摘要派生值。不再扫描任何本地语料目录（`corpus.note_dir/pdf_dir` 已退役），成员与状态以 `bio_paper` 为准。
- **索引只跟踪 PDF**：向量库与引用语料都只认 PDF。笔记与选题产物不进知识库。
- **收录由用户显式决定**：`bio_paper.kb_enabled` 才是「这篇进不进知识库」的开关；上传不再自动全量索引。索引状态由 Java 写，引擎逐篇调 `index_document_bytes` 后经 `/internal/kb/result` 上报 `indexed/failed`；移出走 `remove_document`（只删索引，不动 bio_paper 行与原文）。**不要恢复「上传即全量重建」的老行为**，也不要直接 UPDATE `bio_paper`（强制重建经 `/internal/kb/requeue-all`）。
- **平台表是知识库唯一真相**：`bio_paper` 的 `kb_enabled` / `index_status` / `chunk_count` 由 Java 落盘。引擎每轮索引与启动时对账向量库——不属于任何已加入论文的块删除（含旧版本按镜像绝对路径建的遗留块），已就绪论文的块数与 `chunk_count` 不一致则重建；`failed` 不自动重试。轻量统计用 `document_chunk_counts()`（只读 path，不物化正文）。
- **状态概览不在本包**：知识库统计与论文清单由 Java 查 `bio_paper`；本包只负责检索、分块与索引，不再提供平台表读助手。
- **块里只存干净正文**，「标题 > 章节」前缀在使用点现拼（媒体块的章节位取标题或图注）。把前缀写进块文本会让同一段内容有两个版本。
- **媒体块的文本契约**（写在 `Chunk.text` 的注释里，**改它等于改检索质量**）：图块正文是视觉模型生成的描述，表块正文是版面几何重建出的 markdown 表格 + 视觉描述；图注另存字段，检索前缀与引用核对都用它。描述在索引期生成、**一直开启无开关**，prompt 只转写图上可见内容、禁止推断。
- **配方哈希守恒**：索引状态带配方哈希（切块参数 / 嵌入模型 / 逻辑版本），指纹不符就放弃旧状态全量重扫重嵌。**改切块或嵌入参数不必手工清库，但必须同时改配方输入**，否则新旧块会在同一个库里混合。用户域以平台 `chunk_count` 对账为准，配方升级后由用户触发「全部重新索引」。
- **重索引走定点删旧建新**：按文档标识取旧块 id 清掉再写，不做全表扫描。存储键与块 id 都由文档标识 `paper:<id>` 派生。

## Key Entry Points

- `services/rag_service.py` — 门面与单例
- `services/indexer.py` — 增量索引与一致性恢复
- `services/retriever.py` — 混合检索与重排
- `parsers/chunker.py`、`parsers/pdf_extract.py` — 分块与解析（含字节入口）
- `storage/vector_store.py` — 向量库
- `storage/index_state_store.py` — 索引状态（MySQL，每用户域一行）

## Usage And Change Notes

- **图表原图是软依赖**：原图与应用其余对象共用一个 bucket，但对象名固定 `rag/images/` 前缀（块上只留逻辑键）；孤儿清理只列举该前缀，绝不碰同桶的 `users/` 对象。存储不可达只告警、不拖累文本索引，失败要进冷却（否则每张图都重等一次连接超时）。对应开关关掉即退回「只有文字」。
- **集合结构变更自愈**：启动时比对所需字段，缺字段即删集合重建并提示需全量重建（在老集合上写新字段会直接报错）。改块元数据的字段集后要跑一次真实索引验证。
- **embedding key 缺失时**：检索跳稠密路（退纯 BM25），索引**明确报错**——不要静默产出一半的索引。
- **跨文件常量收 `constants/`**：块 id 规则、块类型词这类被分块 / 索引 / 存储共同消费的契约放这里；只服务单一消费方的正则、提示词、阈值就地声明。
- **评测产物不进本包**：实验脚本与题集在 `scripts/rag/`（不入库），遵循 `goldens/`（题集）+ `results/`（存档）分目录。

## Dependencies And Collaboration

- 消费方：`tools/rag/`（检索、入库、体检、看图工具）；这些工具只装配给 `rag-agent`。
- 依赖 `engine/vision` 取图表区域与视觉描述（core 内部的惰性 import，两者必须同层）。
- 依赖 `engine/llm` 做查询改写与结构化抽取；依赖 `engine/security/services` 的出网守卫。

## Investigation Rule

1. 先读本文件确认问题落在解析、索引还是检索。
2. 门面与单例看 `services/rag_service.py`；扫描与恢复看 `services/indexer.py`；混合检索与改写看 `services/retriever.py` 与 `services/query_rewriter.py`；解析分块看 `parsers/`；存储看 `storage/`。
3. **`read_pdf` 不走本包的索引栈**（走同模块的 markdown 出口，也不占那把全局锁）——排查「读 PDF 慢或卡住」时别先怀疑索引。
4. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/rag -q
docker compose up -d    # 端到端验证与评测需要真实 Milvus + MinIO
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/rag -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)（core manifest）
- 设计依据：ADR 0001（RAG 管线）
- 消费方工具：[`../../tools/AGENTS.md`](../../tools/AGENTS.md)

## References

- [`services/rag_service.py`](services/rag_service.py)
- [`services/indexer.py`](services/indexer.py)
- [`services/retriever.py`](services/retriever.py)
- [`../vision/AGENTS.md`](../vision/AGENTS.md)
