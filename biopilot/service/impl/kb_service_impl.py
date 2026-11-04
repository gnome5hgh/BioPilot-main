"""知识库索引、对账与检索实现。"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from biopilot.common.platform import PlatformError
from biopilot.config import BioPilotConfig
from biopilot.engine.memory.storage.named_lock import NamedLock
from biopilot.engine.rag.constants import (
    IndexOutcomeStatus,
    paper_doc_key,
    paper_id_of,
)
from biopilot.engine.rag.storage.index_state_store import list_domain_states
from biopilot.mapper import kb_file_mapper
from biopilot.mapper.base import shared_db
from biopilot.service import state
from biopilot.service.errors import (
    KbBusyError,
    RequestValidationError,
    ServiceUnavailableError,
)
from biopilot.service.impl.platform_client import shared_platform_client
from biopilot.service.kb_service import KbService

logger = logging.getLogger(__name__)


def _drop_paper_index(svc, paper_id: str) -> None:
    """撤销一篇论文的索引（并发移出后的补偿；失败只留日志）。"""
    try:
        svc.remove_document(paper_doc_key(paper_id))
    except Exception:
        logger.warning("撤回已移出论文的索引失败（%s）", paper_id, exc_info=True)


def _sweep_orphan_vectors(svc, counts: dict[str, int],
                          enabled_ids: set[str]) -> tuple[int, dict[str, int]]:
    """删掉向量库里不属于任何「已加入」论文的块。

    Args:
        svc: RAGService，当前用户域实例。
        counts: 文档标识 → 块数。
        enabled_ids: 仍在知识库的论文 id 集合。

    Returns:
        tuple[int, dict[str, int]]: (删掉的文档数, 剩余「文档标识 → 块数」)。
    """
    remaining = dict(counts)
    removed = 0
    for path in list(remaining):
        pid = paper_id_of(path)
        if pid is not None and pid in enabled_ids:
            continue
        try:
            if svc.remove_document(path):
                removed += 1
                logger.warning("清理孤儿向量：%s（%s）", path, svc.user_domain)
            remaining.pop(path, None)
        except Exception:
            logger.warning("清理孤儿向量失败（%s）", path, exc_info=True)
    return removed, remaining


def _index_summary(**overrides: object) -> dict:
    """构造一次索引轮次的结果摘要（各分支共用，字段齐全）。"""
    summary = {
        "indexed": 0,
        "failed": 0,
        "removed": 0,
        "orphans": 0,
        "drifted": 0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    summary.update(overrides)
    return summary


class KbServiceImpl(KbService):
    """知识库运行时编排。"""

    def __init__(self, runtime=None):
        self._runtime = runtime

    def index_user_kb_sync(self, user_id: str) -> dict:
        """把该用户「已加入知识库」的论文逐篇索引，并清理已移出的论文。"""
        cfg = BioPilotConfig.from_env()
        lock = NamedLock(cfg.runtime.memory_dsn)
        lock_name = f"kb-index:{user_id}"
        acquired = False
        lock_usable = True
        try:
            acquired = lock.acquire(lock_name, timeout=15)
        except Exception:
            # 锁服务异常不阻断索引；降级为无锁执行，状态更新仍有条件守卫。
            lock_usable = False
            logger.warning("知识库索引锁不可用，本轮无锁执行（%s）", user_id,
                           exc_info=True)
        if lock_usable and not acquired:
            return _index_summary(skipped=True)
        try:
            return self._index_user_kb_locked(user_id, cfg)
        finally:
            if acquired:
                lock.release(lock_name)

    def _index_user_kb_locked(self, user_id: str, cfg) -> dict:
        """持有该用户索引锁后执行一轮完整索引（对账 → 逐篇索引 → 清理）。"""
        from biopilot.engine.rag.services.rag_service import get_rag_service

        db = shared_db()
        svc = get_rag_service(cfg, user_domain=user_id, db=db)
        platform = shared_platform_client()

        # ---- 向量库 ↔ 平台表对账（MySQL 是唯一真相） ----
        indexed = failed = removed = orphans = 0
        drift: set[str] = set()
        try:
            vector_counts: dict[str, int] | None = svc.document_chunk_counts()
        except Exception:
            vector_counts = None
            logger.warning("向量库对账读取失败，本轮跳过漂移检测（%s）", user_id,
                           exc_info=True)
        if vector_counts is not None:
            rows = kb_file_mapper.select_papers_for_reconcile(db, user_id)
            enabled_ids = {str(row["id"]) for row in rows if row["kb_enabled"]}
            # 1) 向量库里不属于任何「已加入」论文的块：删掉
            swept, vector_counts = _sweep_orphan_vectors(
                svc, vector_counts, enabled_ids)
            orphans += swept
            # 2) 已就绪论文的向量块数必须与平台 chunk_count 一致
            for row in rows:
                if not row["kb_enabled"] or row["index_status"] != "indexed":
                    continue
                paper_id = str(row["id"])
                expected = int(row.get("chunk_count") or 0)
                actual = vector_counts.get(paper_doc_key(paper_id), 0)
                if actual == 0 or actual != expected:
                    drift.add(paper_id)
                    logger.warning(
                        "论文索引与平台状态不一致，将重建：%s"
                        "（数据库 %d 块，向量库 %d 块）",
                        paper_id, expected, actual)

        seen: set[str] = set()
        for _pass in range(state._KB_INDEX_PASSES):
            # 每遍先让 Java 收敛：半截状态与崩溃遗留的 indexing 都拉回可执行状态。
            try:
                platform.kb_normalize(user_id, requeue_indexing=True)
            except PlatformError as exc:
                logger.info("平台未就绪，知识库对账稍后重试（%s）：%s", user_id, exc)
                return _index_summary(skipped=True, deferred=True,
                                      reason="platform_unavailable")
            except Exception as exc:
                logger.warning("知识库状态收敛失败（%s），本轮跳过：%s", user_id, exc)
                break
            rows = kb_file_mapper.select_papers_for_index(db, user_id)
            enabled = {str(row["id"]): row for row in rows if row["kb_enabled"]}
            todo = []
            for paper_id, row in enabled.items():
                if paper_id in seen:
                    continue
                # 失败等用户显式重试；周期/启动对账不能反复烧嵌入
                if row["index_status"] == "failed":
                    continue
                if row["index_status"] == "indexed" and paper_id not in drift:
                    continue
                todo.append((paper_id, row))
            if not todo:
                break
            try:
                accepted = set(platform.kb_indexing(
                    user_id, [paper_id for paper_id, _row in todo]))
            except PlatformError as exc:
                logger.info("平台未就绪，索引状态置位稍后重试（%s）：%s",
                            user_id, exc)
                break
            except Exception as exc:
                logger.warning("索引状态置位失败（%s），本轮跳过：%s", user_id, exc)
                break
            if not accepted:
                break
            seen.update(accepted)

            results: list[dict] = []
            for paper_id, row in todo:
                if paper_id not in accepted:
                    continue
                try:
                    data, _meta = platform.attachment(user_id, "paper", paper_id)
                    if not data:
                        raise RuntimeError("论文原文取回失败")
                    outcome = svc.index_document_bytes(
                        data, paper_doc_key(paper_id),
                        title=row.get("title") or None)
                    status = getattr(outcome, "status", None)
                    if status == IndexOutcomeStatus.INDEXED:
                        results.append({
                            "paper_id": paper_id, "ok": True,
                            "chunks": int(getattr(outcome, "chunks", 0) or 0),
                            "error": ""})
                    else:
                        reason = (getattr(outcome, "reason", "")
                                  or f"未入库（{status}）")
                        results.append({
                            "paper_id": paper_id, "ok": False,
                            "chunks": 0, "error": reason})
                except Exception as exc:
                    logger.warning("论文索引失败（%s）", paper_id, exc_info=True)
                    results.append({
                        "paper_id": paper_id, "ok": False,
                        "chunks": 0, "error": str(exc)})

            reported = False
            applied: dict = {}
            if results:
                try:
                    applied = platform.kb_result(user_id, results)
                    reported = True
                except PlatformError as exc:
                    logger.info("平台未就绪，索引结果上报稍后重试（%s）：%s",
                                user_id, exc)
                except Exception as exc:
                    # 状态未知：保留已建好的索引，下一轮按 indexing 重排后幂等重建
                    logger.warning("索引结果上报失败（%s）：%s", user_id, exc)

            for item in results:
                paper_id = str(item["paper_id"])
                if not item["ok"]:
                    failed += 1
                    continue
                if not reported:
                    continue
                if applied.get(paper_id):
                    indexed += 1
                else:
                    # 索引期间被移出：撤回刚建好的向量，不留残留
                    _drop_paper_index(svc, paper_id)

        # 已移出知识库（或已删除）的论文：按向量库实际持有的文档标识清理
        rows = kb_file_mapper.select_paper_states(db, user_id)
        enabled = {str(row["id"]) for row in rows if row["kb_enabled"]}
        try:
            counts = svc.document_chunk_counts()
        except Exception:
            counts = {}
            logger.warning("清理已移出论文时读不到向量库（%s），留待下一轮",
                           user_id, exc_info=True)
        swept, _remaining = _sweep_orphan_vectors(svc, counts, enabled)
        removed += swept

        # 收尾再收敛一次（不重排本轮刚置 indexing 的行）
        try:
            platform.kb_normalize(user_id, requeue_indexing=False)
        except PlatformError as exc:
            logger.info("平台未就绪，收尾收敛稍后重试（%s）：%s", user_id, exc)
        except Exception as exc:
            logger.warning("知识库收尾收敛失败（%s）：%s", user_id, exc)

        summary = _index_summary(indexed=indexed, failed=failed, removed=removed,
                                 orphans=orphans, drifted=len(drift))
        state.kb_last_run[user_id] = summary
        return summary

    def users_with_kb(self) -> list[str]:
        """列出知识库里还有勾选论文的用户（启动对账用）。"""
        rows = kb_file_mapper.select_users_with_kb(shared_db())
        return sorted({str(row["user_id"]) for row in rows
                       if row.get("user_id")})

    def users_needing_reconcile(self) -> list[str]:
        """列出知识库派生状态不自洽的用户（启动恢复与周期对账共用）。"""
        rows = kb_file_mapper.select_all_papers(shared_db())
        stale = {
            row["user_id"] for row in rows
            if row.get("user_id") and (
                (int(row.get("kb_enabled") or 0) == 1
                 and str(row.get("index_status") or "")
                 in ("not_added", "queued", "indexing"))
                or (int(row.get("kb_enabled") or 0) == 0 and (
                    int(row.get("indexed") or 0) != 0
                    or str(row.get("index_status") or "not_added") != "not_added"
                    or int(row.get("chunk_count") or 0) != 0
                    or row.get("index_error") is not None
                    or row.get("indexed_at") is not None))
            )
        }
        return sorted(stale | self._users_with_orphan_index(rows))

    def _users_with_orphan_index(self, rows: list[dict]) -> set[str]:
        """按索引状态反查「状态里还记着、平台已不在知识库」的论文归属用户。"""
        enabled: dict[str, set[str]] = {}
        for row in rows:
            user_id = str(row.get("user_id") or "")
            if user_id and int(row.get("kb_enabled") or 0):
                enabled.setdefault(user_id, set()).add(str(row["id"]))
        stale: set[str] = set()
        for domain, docs in list_domain_states(shared_db()).items():
            known = {paper_id_of(key) for key in docs}
            known.discard(None)
            if known - enabled.get(domain, set()):
                stale.add(domain)
        return stale

    async def reconcile_loop(self) -> None:
        """周期对账循环：把跨进程丢失的唤醒、崩溃遗留、半截状态拉回一致。"""
        while True:
            await asyncio.sleep(state._KB_SWEEP_SECONDS)
            try:
                for user_id in await asyncio.to_thread(
                        self.users_needing_reconcile):
                    self.schedule_user_index(user_id)
            except Exception:
                logger.warning("知识库周期对账异常", exc_info=True)

    def schedule_user_index(self, user_id: str) -> None:
        """在事件循环里后台触发一次该用户的知识库索引（singleflight + 补跑）。"""
        if user_id in state.reindex_running:
            state.reindex_pending.add(user_id)
            return
        state.reindex_running.add(user_id)

        async def _runner():
            try:
                misses = 0
                while True:
                    state.reindex_pending.discard(user_id)
                    summary = await asyncio.to_thread(
                        self.index_user_kb_sync, user_id)
                    if summary.get("deferred"):
                        logger.info("平台未就绪，知识库对账交给周期任务（%s）",
                                    user_id)
                        break
                    if summary.get("skipped"):
                        misses += 1
                        if misses > state._KB_LOCK_RETRIES:
                            logger.info("知识库索引锁持续被占用，交给周期对账（%s）",
                                        user_id)
                            break
                        await asyncio.sleep(2)
                        state.reindex_pending.add(user_id)
                    else:
                        misses = 0
                    if user_id not in state.reindex_pending:
                        break
            except Exception:
                logger.warning("知识库索引失败（%s）", user_id, exc_info=True)
            finally:
                state.reindex_running.discard(user_id)

        asyncio.get_running_loop().create_task(_runner())

    async def reindex(self, user_id: str, force: bool) -> dict:
        """重建知识库：默认只补排队/失败/缺文件的论文；force=true 时全部重扫。"""
        if force:
            try:
                await asyncio.to_thread(
                    shared_platform_client().kb_requeue_all, user_id)
            except PlatformError as exc:
                raise ServiceUnavailableError(
                    "索引状态重置失败：平台不可达") from exc
        self.schedule_user_index(user_id)
        return {"status": "started",
                "already_running": user_id in state.reindex_running}

    async def search(self, user_id: str, query: str, top_k) -> dict:
        """试检索：混合 BM25 + 向量，索引持锁时快速失败。"""
        query = (query or "").strip()
        if not query:
            raise RequestValidationError("query 不能为空")
        try:
            top_k = int(top_k or 8)
        except (TypeError, ValueError):
            top_k = 8
        top_k = max(1, min(top_k, 30))
        from biopilot.engine.rag.services.rag_service import get_rag_service

        cfg = BioPilotConfig.from_env()
        svc = get_rag_service(cfg, user_domain=user_id)
        started = _time.monotonic()
        hits = await asyncio.to_thread(
            self._read_locked, svc, svc.retrieve_scored, query, top_k)
        elapsed = int((_time.monotonic() - started) * 1000)
        results = []
        for chunk, score in hits:
            item = self._chunk_view(chunk, score=round(float(score or 0), 4))
            # 只回 paper_id；文件展示字段由 Java 的论文清单在前端 join
            item["paper_id"] = self._paper_id_of(chunk.path)
            results.append(item)
        return {"results": results, "elapsed_ms": elapsed, "query": query}

    async def chunks(self, user_id: str, paper_id: str) -> dict:
        """读取一篇论文的全部分块（索引持锁时快速失败）。"""
        from biopilot.engine.rag.services.rag_service import get_rag_service

        cfg = BioPilotConfig.from_env()
        svc = get_rag_service(cfg, user_domain=user_id, db=shared_db())
        doc_key = paper_doc_key(paper_id)
        chunks = await asyncio.to_thread(
            self._read_locked, svc, svc.list_document_chunks, doc_key)
        chunks.sort(key=lambda chunk: chunk.chunk_index)
        return {"chunks": [self._chunk_view(chunk) for chunk in chunks]}

    def sync(self, user_id: str) -> dict:
        """唤醒一次该用户的知识库索引。"""
        self.schedule_user_index(user_id)
        return {"status": "ok"}

    def runtime(self, user_id: str) -> dict:
        """知识库运行时信息，供 Java 概览合并（纯内存/配置读取）。"""
        cfg = BioPilotConfig.from_env()
        collection = cfg.rag.storage.collection + (
            "" if user_id == "local" else f"_{user_id}")
        return {
            "collection": collection,
            "embedding_model": cfg.rag.embedding.embed_model,
            "running": user_id in state.reindex_running,
            "last_run": state.kb_last_run.get(user_id),
        }

    def _read_locked(self, svc, fn, *args, **kwargs):
        """在 worker 线程里持 RAG 锁执行只读操作，锁被索引占用超限即报错。"""
        if not svc.lock.acquire(timeout=state._KB_LOCK_WAIT_SECONDS):
            raise KbBusyError("知识库正在索引，请稍后再试")
        try:
            return fn(*args, **kwargs)
        finally:
            svc.lock.release()

    def _chunk_view(self, chunk, score=None) -> dict:
        """把 Chunk 转成前端可渲染的字典（正文截断，避免一次返回整篇）。"""
        return {
            "id": chunk.id,
            "text": (chunk.text or "")[:800],
            "path": chunk.path,
            "title": chunk.title,
            "heading": chunk.heading,
            "caption": chunk.caption,
            "chunk_type": chunk.chunk_type,
            "chunk_index": chunk.chunk_index,
            "page": list(chunk.page_num) if chunk.page_num else [],
            "has_image": bool(chunk.image_key),
            "score": score,
        }

    def _paper_id_of(self, doc_key: str) -> str:
        """从文档标识取平台论文 id（检索结果回填用）。"""
        return paper_id_of(doc_key) or Path(doc_key).stem


_service = KbServiceImpl()


def _index_user_kb_locked(user_id: str, cfg) -> dict:
    """兼容旧模块级入口：持锁执行一轮索引。"""
    return _service._index_user_kb_locked(user_id, cfg)
