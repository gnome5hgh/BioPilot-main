"""RagIndexer：把论文 PDF 索引进向量库与 BM25。

索引方式是增量更新：用文档指纹判断哪些论文变了，只重索引新增或变更的论文；
被删除的论文则从索引里清理掉。索引对象只有论文——笔记是 agent 自己的产物，
短、可整篇读，不需要检索（「检索自己的笔记」这项能力是有意移除的）。

索引只有一条内存字节管线（**登录用户域**）：字节由平台适配层取回，不落本地
文件；文档标识是 ``paper:<paper_id>``，指纹是内容摘要派生的数值。成员与状态由
平台表 ``bio_file`` 决定。

幂等设计：单篇文档的重新索引用"先删后建"。因为块 id 由文档标识加序号哈希
生成、与内容无关，文档内容收缩或删掉某些章节时，原来位置上的旧块必须
显式清除，否则会永远残留在索引里。BM25 是向量库文档在内存里的投影，
删除和写入必须与向量库成对执行才能保持一致。

解析来源单一：文本与结构由本地版面解析给出（见 ``biopilot.engine.rag.parsers.pdf_extract``），
抽出的 markdown 再按 ``#`` 行分节；不依赖任何外部解析服务，因此不存在「解析器降级」
这种状态。

媒体块：PDF 的图与表各成一类块，接在章节块之后——表格单元格里的数值与图注里的
结论在章节正文中往往不出现，不独立成块就检索不到。区域定位由 ``vision`` 提供，
本模块只负责把它转成块（存注文与区域内文本，不落图）。

状态版本门控：索引状态记录「配方哈希」（见 ``_recipe_hash``）而非手写版本号。
所有决定「产出哪些块」的配置输入（切块 max/overlap、embed_model）连同
``RECIPE_LOGIC_REVISION`` 一起做 sha256；YAML 里改任一参数即指纹变化 →
下次启动放弃旧状态、全量重扫重嵌——否则旧配方的块会因指纹未变而永远
残留。纯算法逻辑改动无法被参数枚举，改 ``RECIPE_LOGIC_REVISION`` 手动 +1 兜底。

状态存放在 MySQL 的 ``bio_rag_index_state``（每用户域一行，见
``engine/rag/storage/index_state_store.py``）：运行数据根可被清空或重定向，增量依据
必须独立于它。``docs`` 的取值形状保持数值不变（内容摘要派生的浮点指纹），
外部消费方按数值比对做增量跳过。
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from biopilot.engine.rag.constants import (
    CHUNK_ID_LEN, CHUNK_TYPE_FIGURE, CHUNK_TYPE_TABLE, IndexOutcomeStatus, paper_id_of,
)
from biopilot.engine.rag.domain import (
    Chunk,
    IndexOutcome,
    IndexStatus,
    Section,
    indexed_text,
)
from biopilot.engine.rag.parsers.pdf_extract import extract_pdf, extract_pdf_bytes
from biopilot.engine.rag.parsers.table import table_markdown

from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

#: 媒体块描述的并发度：一次全量重建有数百张图，串行会把建索引拖到不可接受
_DESCRIBE_CONCURRENCY = 4

#: 配方哈希的逻辑版本号：切块/解析「算法逻辑」修订号（非参数）。参数
#: （``rag.chunker.*``、embed_model）自动进 ``_recipe_hash`` 指纹；算法逻辑改动
#: （如 ``_pack_sentences`` 改写、章节产出规则变更、丢弃判据词表调整）无法被参数
#: 枚举，只能手动 +1 → 下次重新索引时全量重扫重嵌。仅当切块/解析逻辑改动、
#: 产出块集合可能变化时才改，不要为参数调整而动它。
#: 修订 2：split_doc 新增期刊样板章节（致谢/资助/利益冲突/数据可用性等）与
#: 正文残渣（不成句微碎片）的丢弃判据，产出块集合变小。
#: 修订 3：PDF 解析从外部解析服务换成本地版面解析 + 统一按 ``#`` 行分节，
#: 章节划分与标题来源都变了，产出块集合与文本随之改变。
#: 修订 4：媒体块的文本形态改了——表块由「区域内文字拍平」改为按几何重建的
#: markdown 表格，图块正文置空且改为「有图注才产块」，文本与产出块集合都变。
#: 修订 5：媒体块正文追加视觉模型生成的描述（图块正文不再是空串、表块变成
#: 「markdown + 描述」），块的文本整体改变。
RECIPE_LOGIC_REVISION = 5


def _recipe_hash(cfg) -> str:
    """把「决定产出哪些块」的配置输入散列成状态版本指纹。

    输入四要素：
    - ``RECIPE_LOGIC_REVISION``：切块/解析算法逻辑的手动修订号（参数枚举不到的改动兜底）；
    - ``rag.chunker.max_tokens`` / ``overlap_tokens``：切块窗口参数；
    - ``rag.embedding.embed_model``：换模型（即便同维）旧向量也必须失效，否则新旧
      向量混在同一 Milvus 集合、检索质量静默下降；
    - ``vision.model`` / ``vision.max_tokens``：媒体块正文里的描述由它生成。换模型等于换了
      块的文本；预算则决定截断边界——预算一变，之前被截断的描述会变成另一段文本。两者都不进
      指纹的话，改了设置旧块不会重建，集合里会混着两套描述口径。

    ``sort_keys=True`` 保证同输入稳定；``ensure_ascii=False`` 让中文模型名可读
    （不影响哈希值）。

    Args:
        cfg: BioPilotConfig 实例。

    Returns:
        str: 64 位十六进制 sha256 指纹。
    """
    payload = json.dumps({
        "logic": RECIPE_LOGIC_REVISION,
        "chunk_max_tokens": cfg.rag.chunker.max_tokens,
        "chunk_overlap_tokens": cfg.rag.chunker.overlap_tokens,
        "embed_model": cfg.rag.embedding.embed_model,
        "vision_model": getattr(cfg.vision, "model", ""),
        "vision_max_tokens": getattr(cfg.vision, "max_tokens", 0),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _split_markdown(lines: list[tuple[str, tuple[int, int, int, int, int]]]
                    ) -> tuple[str, list[Section]]:
    """按 ``#`` 行把正文切成章节，顺带取首个一级标题作文档标题。

    Args:
        lines: ``(行文本, 该行的位置)`` 列表。位置为
            ``(页, left, right, top, bottom)``，用于给检索块标注页码与坐标。

    Returns:
        tuple[str, list[Section]]：(文档标题, 章节列表)。标题只认 ``# `` 开头的
        一级标题且取第一个，``##`` 及更深的不算；取不到时为空串。每个章节的位置
        是它覆盖到的行的位置去重后的集合。
    """
    title = ""
    sections: list[Section] = []
    cur_head, cur_body = "", []
    cur_pos: list[tuple[int, int, int, int, int]] = []

    def flush() -> None:
        """把攒着的当前章节收进 sections（位置去重且保持出现顺序）。"""
        if cur_head or cur_body:
            sections.append(Section(cur_head, "\n".join(cur_body),
                                    tuple(dict.fromkeys(cur_pos))))

    for text, pos in lines:
        if text.startswith("#"):
            flush()
            cur_head, cur_body, cur_pos = text.lstrip("# "), [], []   # 去掉 # 和后面的空格
            if not title and text.startswith("# "):
                title = text[2:].strip()
        else:
            cur_body.append(text)
        cur_pos.append(pos)
    flush()
    return title, sections


def _content_stamp(digest: str) -> float:
    """把内容 sha256 转成索引状态里的文档指纹（数值）。

    平台论文没有文件、没有修改时间；状态值仍保持数值形状（外部消费方按数值
    比对），取摘要前 13 个十六进制位转整数——52 位恰好落在 float64 的精确整数
    范围内，内容相同即指纹相同、内容变化即指纹变化。

    Args:
        digest: 内容 sha256 的十六进制串。

    Returns:
        float: 由内容决定的数值指纹。
    """
    return float(int(digest[:13], 16))


@dataclass
class _FileContent:
    """单篇文档解析产物：切块所需的全部原料。

    Attributes:
        title: str，文档标题（版面/元数据标题；取不到为空串）
        sections: list[Section]，章节列表（带各自的版面位置）
    """
    title: str
    sections: list[Section]


class RagIndexer:
    """索引器：维护「文档标识 → 指纹」的索引状态，据此做增量索引。

    职责：
    - 将论文 PDF 字节切块、编码后写入向量库和 BM25。
    - 通过文档指纹判断文档是否变更，只增量更新有变化的文档。
    - 自动清理已被删除的文档的索引数据。
    - 维护索引状态（MySQL ``bio_rag_index_state``，带配方哈希），保证跨进程的增量
      一致性；配方哈希不符时放弃旧状态走全量重扫（切块参数/逻辑升级后的自愈机制）。

    Attributes:
        service: RAGService 单例，与检索器共享底层组件
    """

    def __init__(self, service):
        """绑定门面服务。

        Args:
            service: RAGService 单例，索引器和检索器共享 service 中的组件（向量库、BM25、编码器等）。
        """
        self.service = service

    @property
    def _state_store(self):
        """当前域的索引状态存取器（由服务门面按用户域持有）。

        Returns:
            索引状态存取器。
        """
        return self.service.state_store

    @property
    def _recipe(self) -> str:
        """当前配置的配方指纹——现算不缓存。

        原为 __init__ 快照，构造后 config 被改会得到陈旧指纹、使状态版本比对
        失效；指纹只是 5 个标量的 sha256，现算成本可忽略。

        Returns:
            64 位十六进制 sha256 指纹。
        """
        return _recipe_hash(self.service.config)

    # ---------- 路径/状态工具 ----------
    def read_state(self) -> tuple[object, dict] | None:
        """读原始状态（公开入口；供全量收敛与用户域论文索引判成功）。

        内部路径仍走 _read_state。"""
        return self._read_state()

    def _read_state(self) -> tuple[object, dict] | None:
        """读原始状态，返回 (配方指纹, docs)。

        返回值不做版本判断——版本门控由调用方决定（增量更新要求同版本，
        遇到不符版本的重新索引走全量重扫）。状态存在 MySQL，读不到（无记录 /
        库不可达 / 内容损坏）即视为状态缺失，调用方走全量重扫。

        Returns:
            tuple[object, dict] | None: (version, {文档标识: 指纹})；无状态返回 None。
        """
        return self._state_store.read()

    def _save_state(self, state: dict) -> None:
        """把整份状态按当前配方指纹写入。

        Args:
            state: {文档标识: 指纹} 映射；版本号（配方哈希）由本方法统一补上，
                   调用方只管 docs 内容。**取值形状必须是数值**——本地域的外部
                   消费方按数值比对 mtime，改成对象会使其永远判定「已变更」而
                   静默丢失增量能力。
        """
        self._state_store.write(self._recipe, state)

    def _record_document(self, doc_key: str, stamp: float) -> None:
        """把单篇文档的指纹记进状态（读—改—写在存取器的事务里完成）。

        以平台表为真相，状态只记「索引过哪些论文」，不受配方门控约束；
        配方升级后的全量重扫由用户显式触发「全部重新索引」。

        Args:
            doc_key: 文档标识（``paper:<id>``）。
            stamp: 文档指纹（内容摘要派生值）。
        """

        def _update(current):
            docs = dict(current[1]) if current else {}
            docs[doc_key] = stamp
            return self._recipe, docs

        self._state_store.mutate(_update)

    def _forget_document(self, doc_key: str) -> None:
        """把一篇文档从状态里移除（文档删了、移出知识库或切不出块时）。

        Args:
            doc_key: 文档标识。
        """

        def _update(current):
            if current is None:
                return None
            docs = dict(current[1])
            if doc_key not in docs:
                return None
            docs.pop(doc_key, None)
            return current[0], docs

        self._state_store.mutate(_update)

    # ---------- 文档解析 → 分块 ----------
    def _parse(self, *, path: str | None, data: bytes | None, title: str | None,
               digest: str = "") -> _FileContent:
        """解析一篇 PDF（本地文件或内存字节），产出 chunker 切块所需的全部原料。

        文本与章节由本地版面解析还原成 markdown，再按同一套「按 ``#`` 行分节」逻辑
        切章节。标题由调用方提供（平台论文来自 `bio_file.title`）；本地文件路径
        入口不传标题，标题为空——本模块不再推导标题，绝不用文件名充当标题。

        Args:
            path: PDF 路径；``data`` 为空时用它读文件。
            data: PDF 字节；非空时优先使用（平台论文不落盘）。
            title: 论文标题；None/空表示无标题。
            digest: 字节源的内容 sha256（解析缓存键，与索引状态指纹同源）。

        Returns:
            _FileContent: 解析产物（title/sections）。
        """
        if data is not None:
            extracted = extract_pdf_bytes(data, title or "", digest=digest)
        else:
            extracted = extract_pdf(str(path), title or "")
        # 每个渲染块的位置随它拆出的每一行重复出现，分节后即成为该章节的
        # 位置集合（一个块内的行同属一段，位置相同是准确的）。
        lines: list[tuple[str, tuple[int, int, int, int, int]]] = []
        for blk in extracted.blocks:
            pos = (blk.page, blk.left, blk.right, blk.top, blk.bottom)
            lines.extend((ln, pos) for ln in blk.text.splitlines())
        _, sections = _split_markdown(lines)
        # PDF 的正文里不出现一级标题（级别从二级起），标题只能来自版面/元数据
        return _FileContent(extracted.title or "", sections)

    def _media_chunks(self, doc_key: str, start_index: int,
                      *, pdf: bytes | None = None) -> list[Chunk]:
        """把一篇 PDF 的图/表区域转成检索块，序号接在章节块之后。

        两种媒体块的 `text` 起始取值**不同**（契约写在 `Chunk.text` 的注释里）：

        - **表块**：起点是区域文字按版面几何重建出的 **markdown 表格**（见
          `parsers/table.py`）。重建判据刻意保守，拼不出可信行列时退回纯文字。
        - **图块**：起点是**空串**——图内文字零散（多数字体压根抽不出字），且图内文字本身
          也不构成完整的可检索内容。

        两者随后都会**追加视觉模型生成的描述**（``_enrich_media``）：图块的可检索正文因此
        就是描述本身，表块是「markdown + 描述」。图注（``caption``）始终单独保留——检索前缀
        取它、题集判据与引用核对也用它。

        产块判据按类型分开：表块要求「有表注或有区域文字」，**图块要求「有图注」**——
        没有图注的图不产块。

        **渲染**：先定下哪些区域要成块，再**只对这批**渲染（整篇渲染会为一堆不产块的区域
        白栅格化）。渲染结果供两处用：生成描述（**一直做**）与存入对象存储（由存图开关决定）。
        存储不可达只丢图，块照常入库。

        Args:
            doc_key: 文档标识（进块 id 与元数据）：本地语料是绝对路径，平台论文是
                ``paper:<id>``。
            start_index: 起始块序号（章节块数量），保证 id 空间不重叠。
            pdf: PDF 字节（平台论文）；None 表示按 ``doc_key`` 当作本地路径打开。

        Returns:
            list[Chunk]: 媒体块（图与表，可能为空）。
        """
        source = pdf if pdf is not None else doc_key
        try:
            figures = self.service.extract_figures(source)
        except Exception as e:
            # 图表定位是加分项：失败只丢媒体块，章节块照常入库
            logger.warning("图表区域定位失败，本篇不产媒体块：%s", e)
            return []

        # 惰性 import：vision 有自己的重依赖，不在包导入期拉起
        from biopilot.engine.vision.constants import FigureType

        # 第一遍：定下哪些区域成块（此时不渲染）
        chunks: list[Chunk] = []
        kept: list = []                      # 与 chunks 一一对应的原 Figure，供渲染用
        idx = start_index
        for f in figures:
            caption = " ".join((f.caption or "").split())
            is_table = f.fig_type == FigureType.Table
            if is_table:
                words = list(getattr(f, "image_words", ()) or ())
                body = table_markdown(words)
                if body is None:
                    # 重建判据不过（列数抖动/单行/词框重叠）→ 退回纯文字：不声称自己有结构。
                    # 记一条 debug 便于回答「为什么这块没出表格」。
                    body = " ".join(t for t, _b in words if (t or "").strip())
                    if body:
                        logger.debug("表格结构重建未通过判据，退回纯文字（%s 第 %s 页）",
                                     doc_key, f.page + 1)
                if not caption and not body:
                    continue
            else:
                body = ""                      # 图块正文从空起，视觉描述在 _enrich_media 里追加
                if not caption:
                    continue
            ctype = CHUNK_TYPE_TABLE if is_table else CHUNK_TYPE_FIGURE
            bounds = f.region_boundary
            position = ((f.page + 1, int(bounds.x1), int(bounds.x2),
                         int(bounds.y1), int(bounds.y2)),) if bounds else ()
            chunk_id = hashlib.sha1(f"{doc_key}:{idx}".encode()).hexdigest()[:CHUNK_ID_LEN]
            chunks.append(Chunk(
                id=chunk_id, text=body, path=doc_key, heading="", caption=caption,
                chunk_type=ctype, position=position, chunk_index=idx,
            ))
            kept.append(f)
            idx += 1

        self._enrich_media(doc_key, chunks, kept, pdf=pdf)
        return chunks

    def _enrich_media(self, doc_key: str, chunks: list[Chunk], figures: list,
                      *, pdf: bytes | None = None) -> None:
        """渲染入选区域 → 给媒体块追加视觉描述 →（可选）把原图存进对象存储。

        三步的失败面互相独立、都**只降级不抛**：渲染失败则这篇的媒体块既不带描述也不落图；
        描述失败逐块退回原形态；存储不可达只丢图。索引不能因为「加分项」而失败。

        Args:
            doc_key: 文档标识（本地绝对路径或 ``paper:<id>``）。
            chunks: 媒体块（就地追加描述、回填 ``image_key``）。
            figures: 与 ``chunks`` 一一对应的原 Figure 列表。
            pdf: PDF 字节（平台论文）；None 表示按 ``doc_key`` 当作本地路径打开。
        """
        if not chunks:
            return
        try:
            # 一次打开、批量渲染这批区域（逐个渲染会把同一篇 PDF 反复打开）
            self.service.render_figures(pdf if pdf is not None else doc_key, figures)
        except Exception as e:
            logger.warning("图表区域渲染失败，本篇媒体块不带描述也不落图：%s", e)
            return
        self._append_descriptions(chunks, figures)
        self._store_images(chunks, figures)

    def _append_descriptions(self, chunks: list[Chunk], figures: list) -> None:
        """给媒体块正文追加视觉模型生成的描述（图块 = 描述，表块 = markdown + 描述）。

        描述**一直开启、没有开关**：图块正文若不带它，就只剩「标题 > 图注」可检索，
        实测 12 条图块题一个都召不回（正文块会把槽位占满）。视觉模型不可用时整批跳过并
        告警——块照常入库，只是退回没有描述的形态。

        并发跑（一次全量重建有数百张图，串行会把建索引拖到不可接受）；单张失败只让那一块
        退回原形态。
        """
        from biopilot.engine.vision.services.describer import FigureDescriber

        describer = FigureDescriber(self.service.config)
        if not describer.available:
            logger.warning("视觉模型未配置，媒体块不带描述入库（图块将只剩图注可检索）")
            return

        def _one(figure):
            try:
                return describer.describe(figure)
            except Exception as e:              # noqa: BLE001 —— 单张失败不阻断该篇其它块
                logger.warning("媒体块描述失败，该块退回原形态：%s", e)
                return ""

        with ThreadPoolExecutor(max_workers=_DESCRIBE_CONCURRENCY) as pool:
            descriptions = list(pool.map(_one, figures))
        for chunk, desc in zip(chunks, descriptions):
            if desc:
                chunk.text = f"{chunk.text}\n{desc}" if chunk.text else desc

    def _store_images(self, chunks: list[Chunk], figures: list) -> None:
        """把媒体块的原图存进对象存储，并在块上回写对象键。

        开关关掉 / 存储不可达 / 单块无字节都只丢图，块照常入库。

        Args:
            chunks: 已渲染的媒体块（就地回填 `image_key`）。
            figures: 与 `chunks` 一一对应的原 Figure 列表。
        """
        store = self.service.image_store
        if not getattr(store, "enabled", False):
            return
        for chunk, figure in zip(chunks, figures):
            data = getattr(figure, "image_bytes", b"") or b""
            if not data:
                continue                       # 区域为空或渲染没产出图
            key = f"{chunk.id}.png"
            if store.put(key, data):
                chunk.image_key = key


    def _collect_media_keys(self, chunk_ids: list[str]) -> list[str]:
        """取出这些块上记的图表原图对象键（在块行被删掉**之前**调用）。

        键取块行上的 `image_key`，不靠「按块 id 猜命名」——命名规则将来变了也不会删错。
        开关关掉 / 查询失败都返回空列表（调用方据此跳过删对象）。

        Args:
            chunk_ids: 要清理的块 id 列表。

        Returns:
            list[str]: 这些块引用的对象键。
        """
        store = self.service.image_store
        if not chunk_ids or not getattr(store, "enabled", False):
            return []
        try:
            rows = self.service._ensure_vector_store().fetch_by_ids(chunk_ids)
        except Exception as e:
            logger.warning("清理图表原图时查不到旧块，跳过删图：%s", e)
            return []
        return [c.image_key for c in rows if c.image_key]

    def _remove_media_objects(self, keys: list[str]) -> None:
        """按对象键把图表原图从对象存储里删掉（在块行删掉**之后**调用）。

        顺序是刻意的：**先删库行、再删对象**。反过来的话，一旦删行失败，库里就留下一个
        指向已删对象的坏块（查得到、图打不开）；而对象多留一会儿无害——真成了孤儿，
        下次全量收敛会扫掉。

        Args:
            keys: 要删除的对象键列表。
        """
        if not keys:
            return
        store = self.service.image_store
        for key in keys:
            store.remove(key)

    def _sweep_orphan_images(self) -> int:
        """删掉「图片命名空间里有、库里已无对应块」的孤儿对象（全量收敛用）。

        图片与平台文件共用一个 bucket，所以这里只接受图片的逻辑键（块 id 命名、
        不含路径分隔符）。``list_keys`` 已按图片前缀列举，这一层再兜一次底：
        万一将来替身或新实现返回了 ``users/...`` 之类的键，也不会被当成孤儿删掉。

        Returns:
            int: 清掉的对象数；拿不到清单时返回 0（宁可少删，不可误删）。
        """
        store = self.service.image_store
        if not getattr(store, "enabled", False):
            return 0
        keys = {key for key in store.list_keys() if "/" not in key}
        if not keys:
            return 0
        try:
            live = {c.image_key for c, _mtime in
                    self.service._ensure_vector_store().all_documents() if c.image_key}
        except Exception as e:
            logger.warning("全量收敛取不到库内对象键，跳过孤儿清理：%s", e)
            return 0
        orphans = keys - live
        for key in orphans:
            store.remove(key)
        return len(orphans)

    def _embed_chunks(self, chunks: list[Chunk]):
        """把一批块编码成向量（供写入向量库）。

        编码用的是带前缀的文本（`indexed_text`），与 BM25 侧的输入同源——库里存的
        则是干净正文。

        Args:
            chunks: Chunk 对象列表。

        Returns:
            np.ndarray: 向量矩阵，形状为 (len(chunks), dim)。
        """
        embedder = self.service._ensure_embedder()
        vecs = embedder([indexed_text(c) for c in chunks])
        return vecs

    def _derive_state_from_store(self, store) -> dict:
        """从向量库的元数据重建索引状态（当状态记录丢失时使用）。

        向量库里每个块都带其所属文档的**文档标识**与指纹；同一文档的多个块
        共享同一指纹，因此取最大值即可。

        Args:
            store: VectorStore 实例。

        Returns:
            dict: {文档标识: 指纹}，用于后续增量比对。
        """
        state: dict = {}
        for chunk, mtime in store.all_documents():
            # 同一文档可能有多块，取最大的指纹
            if chunk.path not in state or mtime > state[chunk.path]:
                state[chunk.path] = mtime
        return state

    # ---------- 公开 API ----------
    def index_document_bytes(self, data: bytes, doc_key: str,
                             title: str | None = None) -> IndexOutcome:
        """单篇平台论文（内存字节）的增量重索引，不落本地文件。

        文档标识由调用方按 ``paper:<paper_id>`` 拼好：块 id、向量库 path 字段与
        索引状态键都用它。内容指纹取 sha256 派生的数值——平台论文没有 mtime，
        同一篇重复索引按内容判定是否变化。

        Args:
            data: PDF 字节。
            doc_key: 文档标识（``paper:<paper_id>``）。
            title: 论文标题（来自平台表）。

        Returns:
            IndexOutcome，本次入库的状态、写入块数与原因。
        """
        if not data:
            return IndexOutcome(IndexOutcomeStatus.EMPTY, reason="原文为空")
        digest = hashlib.sha256(data).hexdigest()
        return self._index(
            doc_key, path=None, data=data, title=title,
            stamp=_content_stamp(digest), is_pdf=True, digest=digest)

    def _index(self, doc_key: str, *, path: str | None, data: bytes | None,
               title: str | None, stamp: float, is_pdf: bool,
               digest: str = "") -> IndexOutcome:
        """单篇文档的索引主流程（平台论文与评测脚本的内存字节共用）。

        Args:
            doc_key: 文档标识（进块 id、Chunk.path 与状态键）。
            path: 本地文件路径；``data`` 为空时使用。
            data: PDF 字节；非空时优先使用。
            title: 论文标题（可为 None）。
            stamp: 文档指纹（本地 mtime 或内容摘要派生值）。
            is_pdf: 是否按 PDF 追加媒体块。
            digest: 字节源的内容 sha256（解析缓存键）。

        Returns:
            IndexOutcome，本次入库的状态、块数与原因。
        """
        # 1. 解析文档，获得切块原料（章节 + 标题）
        parsed = self._parse(path=path, data=data, title=title, digest=digest)
        store = self.service._ensure_vector_store()
        bm25 = self.service._ensure_bm25()

        # 2. 清除该文档的旧索引（定点查询替代全表扫描）。存储键与块 id 都用文档标识。
        #    图的键要先从旧块行上取下来（行删了就查不到键），但**对象要等行删完再删**——
        #    顺序反过来的话，删行失败会留下指向已删对象的坏块。
        old_ids = store.doc_chunk_ids(doc_key)
        old_image_keys = self._collect_media_keys(old_ids)
        for did in old_ids:
            bm25.remove_document(did)
        store.delete_doc(doc_key)
        self._remove_media_objects(old_image_keys)

        # 3. 切分：章节块 + 图/表媒体块，过滤空白块
        chunks = self.service.chunker.split_doc(doc_key, parsed.sections, title=parsed.title)
        if is_pdf:
            chunks.extend(self._media_chunks(doc_key, start_index=len(chunks), pdf=data))
        chunks = [c for c in chunks if c.text.strip() or c.caption.strip()]
        if not chunks:
            # 文档被清空：旧块已删，无需写新内容（状态不动，下次扫描会重试）
            return IndexOutcome(IndexOutcomeStatus.EMPTY, reason="切块后无内容（旧块已清理）")

        # 4. 编码并写入
        vecs = self._embed_chunks(chunks)
        # 向量数据库存：① 块正文；② 正文（带前缀）压缩成的一个 1024 维浮点向量；③ 元数据
        store.upsert(chunks, vecs, mtime=stamp)
        # bm25存的是：① 带前缀文本分词后的 token 列表，比如：["多意图","执行","clarification","触发","判定",...]；② 词频矩阵 + idf 表（“这个词在几篇文档里出现过”的统计）
        bm25.add_documents([(c.id, indexed_text(c)) for c in chunks])

        # 5. 记录状态（本地域带配方门控，见 _record_document）
        self._record_document(doc_key, stamp)

        return IndexOutcome(IndexOutcomeStatus.INDEXED, chunks=len(chunks))

    def remove_document(self, doc_key: str) -> bool:
        """把一篇文档从索引里整体移除（不动磁盘文件与平台论文行）。

        与 index_document_bytes 的「先删后建」共用同一套清理动作：按文档标识定点取块 id，
        删 BM25 行、向量行、图表对象，最后从状态里移除该文档。用于「移出知识库
        但保留平台行」——只删这一篇的索引，不重扫其他文档。

        Args:
            doc_key: 文档标识（``paper:<paper_id>``）。

        Returns:
            bool: 执行了移除时为 True。
        """
        key = doc_key if paper_id_of(doc_key) else str(Path(doc_key).resolve())
        store = self.service._ensure_vector_store()
        bm25 = self.service._ensure_bm25()
        chunk_ids = store.doc_chunk_ids(key)
        image_keys = self._collect_media_keys(chunk_ids)
        for chunk_id in chunk_ids:
            bm25.remove_document(chunk_id)
        store.delete_doc(key)
        self._remove_media_objects(image_keys)
        self._forget_document(key)
        return True

    def status(self) -> IndexStatus:
        """体检：把索引状态、向量库、关键词索引对照一遍（只读）。

        本地目录语料已退役：只报告平台论文索引的状态与库侧计数，不扫任何磁盘目录。
        发现不一致时由调用方决定是否让平台重新排队索引。

        Returns:
            IndexStatus 快照。Milvus 不可达时库侧三个计数留 0（避免为探测白等 RPC 超时）。
        """
        st = IndexStatus(recipe=self._recipe, milvus_ok=self.service.milvus_available())

        raw = self._read_state()
        if raw is not None:
            version, docs = raw
            st.state_present = True
            st.state_version = version
            st.recipe_in_sync = version == st.recipe
            st.indexed_docs = len(docs)

        if st.milvus_ok:
            store = self.service._ensure_vector_store()
            st.store_chunks = store.count()
            # all_documents() 的每项是 (块, mtime)，文档身份取块路径
            st.store_docs = len({c.path for c, _ in store.all_documents()})
            st.bm25_docs = self.service._ensure_bm25().count()
        return st
