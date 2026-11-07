"""``bio_rag_paper_status`` 的读写 SQL：论文索引状态的唯一落点（Python 独占写）。

索引状态（排队/索引中/成功/失败、块数）由引擎在索引流程里就地维护，不再向平台
上报转抄；``bio_file`` 只保留勾选真相 ``kb_enabled``（Java 写）。本模块的全部读
查询都以 LEFT JOIN ``bio_file`` 的方式带上勾选——写入侧的条件守卫（kb_enabled=1）
同样靠 JOIN 完成：索引期间被移出的论文，结果落不进状态表，引擎据此撤回向量。

「未加入知识库」不落行：行存在即代表该论文进入过索引流程；勾选被移出或论文被
删除后，遗留行由 :func:`normalize` 的 reset 步骤清掉。
"""
from __future__ import annotations

from datetime import datetime, timezone

#: 失败原因在表里的截断长度（与列定义一致）
_ERROR_LIMIT = 500

# JOIN 片段：状态行必须始终对照勾选真相（bio_file.kb_enabled，Java 写）。
_JOIN_ENABLED_FILE = (
    " JOIN bio_file f ON f.kind='paper' AND f.user_id=s.user_id AND f.id=s.paper_id"
    " AND f.kb_enabled=1"
)


def _now() -> str:
    """当前 UTC 时间的 ISO 字符串（与引擎其余表的 updated_at 同口径）。"""
    return datetime.now(timezone.utc).isoformat()


# ---------- 读（索引流程与对账用，全部只读 bio_file 的身份/勾选/标题列） ----------

def select_for_reconcile(db, user_id: str):
    """取对账所需的论文行：勾选 + 当前索引状态 + 块数。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。

    Returns:
        list[dict]: 每项含 id/kb_enabled/index_status/chunk_count（无状态行时
        后两列为 NULL）。
    """
    return db.execute(
        "SELECT f.id, f.kb_enabled, s.index_status, s.chunk_count"
        " FROM bio_file f LEFT JOIN bio_rag_paper_status s"
        " ON s.user_id=f.user_id AND s.paper_id=f.id"
        " WHERE f.kind='paper' AND f.user_id=?", (user_id,)).fetchall()


def select_papers_for_index(db, user_id: str):
    """取索引所需的论文行（含 OSS 键与标题）。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。

    Returns:
        list[dict]: 每项含 id/oss_key/kb_enabled/index_status/title。
    """
    return db.execute(
        "SELECT f.id, f.oss_key, f.kb_enabled, s.index_status, f.title"
        " FROM bio_file f LEFT JOIN bio_rag_paper_status s"
        " ON s.user_id=f.user_id AND s.paper_id=f.id"
        " WHERE f.kind='paper' AND f.user_id=?", (user_id,)).fetchall()


def select_paper_states(db, user_id: str):
    """取论文 id 与是否加入知识库（清理已移出论文用）。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。

    Returns:
        list[dict]: 每项含 id/kb_enabled。
    """
    return db.execute(
        "SELECT id, kb_enabled FROM bio_file WHERE kind='paper' AND user_id=?",
        (user_id,)).fetchall()


def select_all_papers(db):
    """取全量论文的勾选与状态（启动/周期对账用，跨用户）。

    Args:
        db: MemoryDB，连接池。

    Returns:
        list[dict]: 每项含 user_id/id/kb_enabled/paper_id/index_status/indexed/
        index_error/indexed_at/chunk_count（无状态行时状态列为 NULL）。
    """
    return db.execute(
        "SELECT f.user_id, f.id, f.kb_enabled, s.paper_id, s.index_status,"
        " s.indexed, s.index_error, s.indexed_at, s.chunk_count"
        " FROM bio_file f LEFT JOIN bio_rag_paper_status s"
        " ON s.user_id=f.user_id AND s.paper_id=f.id WHERE f.kind='paper'"
    ).fetchall()


def select_users_with_kb(db):
    """列出知识库里还有勾选论文的用户（启动对账用）。

    Args:
        db: MemoryDB，连接池。

    Returns:
        list[dict]: 每项含 user_id。
    """
    return db.execute(
        "SELECT DISTINCT user_id FROM bio_file"
        " WHERE kind='paper' AND kb_enabled=1").fetchall()


def select_users_with_orphan_rows(db):
    """列出状态行指向已删除论文的用户（孤儿行要靠下一轮 normalize 清掉）。

    Args:
        db: MemoryDB，连接池。

    Returns:
        list[dict]: 每项含 user_id。
    """
    return db.execute(
        "SELECT DISTINCT s.user_id FROM bio_rag_paper_status s"
        " LEFT JOIN bio_file f ON f.kind='paper' AND f.user_id=s.user_id"
        " AND f.id=s.paper_id WHERE f.id IS NULL").fetchall()


# ---------- 写（引擎独占；每轮索引在 NamedLock 内调用） ----------

def normalize(db, user_id: str, *, requeue_indexing: bool) -> dict:
    """把状态行收敛到勾选真相，返回各步影响行数。

    三步语义与旧 Java 状态机一致：
    - **reset**：删掉「已移出知识库或论文已删除」的状态行（未加入=无行）；
    - **queued**：为已勾选但没有状态行的论文补一条 queued（INSERT IGNORE，
      已有 indexed/failed 行的论文不受影响——已就绪不打回重做，失败不自动重试）；
    - **requeued**：把崩溃遗留的 indexing 拉回 queued，仅持索引锁的调用方
      （每轮索引流程）才允许，否则另一个进程可能正在索引。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。
        requeue_indexing: 是否重排遗留的 indexing 行。

    Returns:
        dict: ``{reset, queued, requeued}`` 各自影响的行数。
    """
    now = _now()
    with db.transaction():
        # 已移出/已删除的论文：行即孤儿，直接删
        reset = db.execute(
            "DELETE s FROM bio_rag_paper_status s LEFT JOIN bio_file f"
            " ON f.kind='paper' AND f.user_id=s.user_id AND f.id=s.paper_id"
            " WHERE s.user_id=? AND (f.id IS NULL OR f.kb_enabled=0)",
            (user_id,)).rowcount
        # 已勾选但从未入过流程的论文：补 queued 占位
        queued = db.execute(
            "INSERT IGNORE INTO bio_rag_paper_status"
            " (user_id, paper_id, index_status, indexed, chunk_count, updated_at)"
            " SELECT f.user_id, f.id, 'queued', 0, 0, ? FROM bio_file f"
            " WHERE f.kind='paper' AND f.user_id=? AND f.kb_enabled=1",
            (now, user_id)).rowcount
        requeued = 0
        if requeue_indexing:
            requeued = db.execute(
                "UPDATE bio_rag_paper_status s" + _JOIN_ENABLED_FILE
                + " SET s.index_status='queued', s.index_error=NULL, s.updated_at=?"
                " WHERE s.user_id=? AND s.index_status='indexing'",
                (now, user_id)).rowcount
    return {"reset": reset, "queued": queued, "requeued": requeued}


def mark_indexing(db, user_id: str, paper_ids: list[str]) -> list[str]:
    """把仍勾选的论文置为「索引中」，返回被接受的论文 id。

    与旧 Java 状态机同语义：只要当前 ``kb_enabled=1`` 就接受（不卡状态值——
    漂移重建的论文当前是 indexed，也要放行重索引）；索引期间被移出的论文自然
    被拒绝。行缺失时按 queued 补建（upsert），保证勾选后未经 normalize 的路径
    也能入流程。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。
        paper_ids: 本批待索引论文 id。

    Returns:
        list[str]: 被接受（kb_enabled=1）的论文 id。
    """
    ids = [str(pid) for pid in (paper_ids or []) if str(pid).strip()]
    if not ids:
        return []
    now = _now()
    accepted = [
        str(row["id"]) for row in db.execute(
            "SELECT f.id FROM bio_file f WHERE f.kind='paper' AND f.user_id=?"
            " AND f.kb_enabled=1 AND f.id IN (%s)" % ",".join(["?"] * len(ids)),
            (user_id, *ids)).fetchall()
    ]
    if not accepted:
        return []
    with db.transaction():
        for paper_id in accepted:
            db.execute(
                "INSERT INTO bio_rag_paper_status"
                " (user_id, paper_id, index_status, indexed, chunk_count, updated_at)"
                " VALUES (?, ?, 'indexing', 0, 0, ?)"
                " ON DUPLICATE KEY UPDATE index_status='indexing', index_error=NULL,"
                " updated_at=VALUES(updated_at)",
                (user_id, paper_id, now))
    return accepted


def apply_results(db, user_id: str, results: list[dict]) -> dict:
    """批量写入索引结果，返回每篇是否真正落盘。

    落盘条件与旧 Java 状态机一致：当前仍是 ``indexing`` 且论文仍勾选——
    索引期间被移出（或被重新排队）的论文结果被拒绝，调用方据此撤回刚建好的
    向量。未落盘的论文状态行保持原样，下一轮按原状态处理。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。
        results: 每项 ``{paper_id, ok, chunks, error}``。

    Returns:
        dict: paper_id → 是否落盘。
    """
    applied: dict = {}
    now = _now()
    with db.transaction():
        for item in results or []:
            paper_id = str(item.get("paper_id") or "").strip()
            if not paper_id:
                continue
            ok = bool(item.get("ok"))
            if ok:
                rows = db.execute(
                    "UPDATE bio_rag_paper_status s" + _JOIN_ENABLED_FILE
                    + " SET s.indexed=1, s.index_status='indexed', s.index_error=NULL,"
                    " s.indexed_at=?, s.chunk_count=?, s.updated_at=?"
                    " WHERE s.user_id=? AND s.paper_id=? AND s.index_status='indexing'",
                    (now, max(0, int(item.get("chunks") or 0)), now, user_id,
                     paper_id)).rowcount
            else:
                error = str(item.get("error") or "")[:_ERROR_LIMIT]
                rows = db.execute(
                    "UPDATE bio_rag_paper_status s" + _JOIN_ENABLED_FILE
                    + " SET s.indexed=0, s.index_status='failed', s.index_error=?,"
                    " s.chunk_count=0, s.updated_at=?"
                    " WHERE s.user_id=? AND s.paper_id=? AND s.index_status='indexing'",
                    (error, now, user_id, paper_id)).rowcount
            applied[paper_id] = rows > 0
    return applied


def requeue_all(db, user_id: str) -> int:
    """把该用户所有已勾选论文重排为 queued（强制重建）。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。

    Returns:
        int: 实际重排的行数。
    """
    return db.execute(
        "UPDATE bio_rag_paper_status s" + _JOIN_ENABLED_FILE
        + " SET s.index_status='queued', s.index_error=NULL, s.updated_at=?"
        " WHERE s.user_id=?",
        (_now(), user_id)).rowcount


def requeue(db, user_id: str, paper_ids: list[str]) -> int:
    """把指定论文重排为 queued（失败重试与标题变更重建共用）。

    行缺失且论文仍勾选时补建 queued 行；已勾选的论文无论当前状态一律重排
    （与旧 Java retry/requeue 同语义：不做状态守卫，由调用方保证语义）。

    Args:
        db: MemoryDB，连接池。
        user_id: 归属用户。
        paper_ids: 要重排的论文 id。

    Returns:
        int: 重排（含补建）的行数。
    """
    ids = [str(pid) for pid in (paper_ids or []) if str(pid).strip()]
    if not ids:
        return 0
    now = _now()
    total = 0
    with db.transaction():
        for paper_id in ids:
            db.execute(
                "INSERT IGNORE INTO bio_rag_paper_status"
                " (user_id, paper_id, index_status, indexed, chunk_count, updated_at)"
                " SELECT f.user_id, f.id, 'queued', 0, 0, ? FROM bio_file f"
                " WHERE f.kind='paper' AND f.user_id=? AND f.kb_enabled=1 AND f.id=?",
                (now, user_id, paper_id))
            total += db.execute(
                "UPDATE bio_rag_paper_status s" + _JOIN_ENABLED_FILE
                + " SET s.index_status='queued', s.index_error=NULL, s.updated_at=?"
                " WHERE s.user_id=? AND s.paper_id=?",
                (now, user_id, paper_id)).rowcount
    return total


def delete_by_user(db, user_id: str):
    """删除某用户的全部状态行（删户清理）。"""
    return db.execute(
        "DELETE FROM bio_rag_paper_status WHERE user_id=?", (user_id,))
