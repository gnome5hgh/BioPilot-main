"""bio_paper 的索引状态列（Python 引擎独占写者）。

平台侧（Java 或过渡适配层）只写论文身份/文件列与 `kb_enabled`；`indexed` /
`index_status` / `index_error` / `indexed_at` / `chunk_count` 由本模块维护。
这样索引状态机只有一个写者，跨栈迁移时不会出现两边同时改状态。
"""
from __future__ import annotations

from datetime import datetime, timezone

from biopilot.core.memory.storage.database import MemoryDB

__all__ = [
    "set_kb_enabled", "queue_papers", "detach_papers",
    "mark_indexing", "mark_index_result", "mark_not_added",
    "kb_counts", "paper_map",
]


def _now() -> str:
    """当前 UTC ISO 时间串。"""
    return datetime.now(timezone.utc).isoformat()


def set_kb_enabled(db: MemoryDB, user_id: str, paper_ids: list[str],
                   enabled: bool) -> int:
    """批量把论文加入/移出知识库，返回实际更新的行数。

    加入 = `kb_enabled` 置 1、状态排队；移出 = 清空索引结果并回到 not_added。
    真正的索引/清理由调用方在拿到返回后触发。

    Args:
        db: 记忆库连接。
        user_id: 归属用户。
        paper_ids: 论文 id 列表。
        enabled: True 加入，False 移出。

    Returns:
        int，实际更新的行数。
    """
    ids = [str(item) for item in paper_ids if item]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    if enabled:
        result = db.execute(
            f"UPDATE bio_paper SET kb_enabled=1, index_status='queued', index_error=NULL"
            f" WHERE user_id=? AND id IN ({placeholders})",
            (user_id, *ids))
    else:
        result = db.execute(
            f"UPDATE bio_paper SET kb_enabled=0, indexed=0, index_status='not_added',"
            f" index_error=NULL, chunk_count=0"
            f" WHERE user_id=? AND id IN ({placeholders})",
            (user_id, *ids))
    return int(getattr(result, "rowcount", 0) or 0)


def queue_papers(db: MemoryDB, user_id: str, paper_ids: list[str]) -> None:
    """把论文状态置为排队（Java 侧写完 kb_enabled 后调内部接口触发）。"""
    ids = [str(item) for item in paper_ids if item]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    db.execute(
        f"UPDATE bio_paper SET index_status='queued', index_error=NULL"
        f" WHERE user_id=? AND id IN ({placeholders})",
        (user_id, *ids))


def detach_papers(db: MemoryDB, user_id: str, paper_ids: list[str]) -> None:
    """把论文回退为未加入知识库并清空索引状态（Java 侧移出后调内部接口）。"""
    ids = [str(item) for item in paper_ids if item]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    db.execute(
        f"UPDATE bio_paper SET kb_enabled=0, indexed=0, index_status='not_added',"
        f" index_error=NULL, chunk_count=0"
        f" WHERE user_id=? AND id IN ({placeholders})",
        (user_id, *ids))


def mark_indexing(db: MemoryDB, user_id: str, paper_ids: list[str]) -> None:
    """把论文状态置为「索引中」（批处理开始时一次）。"""
    ids = [str(item) for item in paper_ids if item]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    db.execute(
        f"UPDATE bio_paper SET index_status='indexing', index_error=NULL"
        f" WHERE user_id=? AND id IN ({placeholders})",
        (user_id, *ids))


def mark_index_result(db: MemoryDB, user_id: str, paper_id: str, ok: bool,
                      chunks: int = 0, error: str = "") -> None:
    """写入单篇论文的索引结果（成功置 indexed + 分块数，失败留原因）。"""
    if ok:
        db.execute(
            "UPDATE bio_paper SET indexed=1, index_status='indexed', index_error=NULL,"
            " indexed_at=?, chunk_count=? WHERE user_id=? AND id=?",
            (_now(), int(chunks or 0), user_id, paper_id))
    else:
        db.execute(
            "UPDATE bio_paper SET indexed=0, index_status='failed', index_error=?,"
            " chunk_count=0 WHERE user_id=? AND id=?",
            ((error or "索引失败")[:500], user_id, paper_id))


def mark_not_added(db: MemoryDB, user_id: str, paper_id: str) -> None:
    """把论文回退为「未加入知识库」（移出成功或清索引后）。"""
    db.execute(
        "UPDATE bio_paper SET kb_enabled=0, indexed=0, index_status='not_added',"
        " index_error=NULL, chunk_count=0 WHERE user_id=? AND id=?",
        (user_id, paper_id))


def kb_counts(db: MemoryDB, user_id: str) -> dict:
    """知识库状态快照：论文总数/收录/各索引状态/分块数。"""
    rows = db.execute(
        "SELECT kb_enabled, index_status, chunk_count FROM bio_paper WHERE user_id=?",
        (user_id,)).fetchall()
    counts = {
        "total": len(rows), "kb_enabled": 0, "indexed": 0, "queued": 0,
        "indexing": 0, "failed": 0, "not_added": 0, "chunks": 0,
    }
    for row in rows:
        if int(row.get("kb_enabled") or 0):
            counts["kb_enabled"] += 1
        status = row.get("index_status") or (
            "indexed" if int(row.get("kb_enabled") or 0) else "not_added")
        if status in counts:
            counts[status] += 1
        counts["chunks"] += int(row.get("chunk_count") or 0)
    return counts


def paper_map(db: MemoryDB, user_id: str) -> dict:
    """paper_id → {id,title,file_name}；供 KB 检索结果回填展示字段。"""
    rows = db.execute(
        "SELECT id, title, file_name FROM bio_paper WHERE user_id=?",
        (user_id,)).fetchall()
    return {row["id"]: dict(row) for row in rows}
