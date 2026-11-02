"""`bio_paper` 索引状态的只读视图。

索引列的写者是 Java（`KbStateService` + `PaperService`）：勾选/移出与状态复位在同一
条 UPDATE 里完成，索引过程中的 `indexing` / `indexed` / `failed` 也由引擎经
``/internal/kb/indexing`` 与 ``/internal/kb/result`` 交给 Java 落盘。本模块只负责
状态概览与展示字段的读取，**不写任何平台表**。
"""
from __future__ import annotations

from biopilot.core.memory.storage.database import MemoryDB

__all__ = ["kb_counts", "paper_map"]


def kb_counts(db: MemoryDB, user_id: str) -> dict:
    """知识库状态快照：论文总数/收录/各索引状态/分块数。

    状态桶与分块数只统计仍在知识库里的行（`kb_enabled=1`）。派生列可能因历史
    写入残留旧值（如已移出但 index_status 还是 indexed），以勾选状态为准统计，
    才能与「已加入」清单、试检索的实际命中面保持一致；未加入的行一律记入
    not_added。

    Args:
        db: 记忆库连接。
        user_id: 归属用户。

    Returns:
        dict，含 total/kb_enabled/indexed/queued/indexing/failed/not_added/chunks。
    """
    rows = db.execute(
        "SELECT kb_enabled, index_status, chunk_count FROM bio_paper WHERE user_id=?",
        (user_id,)).fetchall()
    counts = {
        "total": len(rows), "kb_enabled": 0, "indexed": 0, "queued": 0,
        "indexing": 0, "failed": 0, "not_added": 0, "chunks": 0,
    }
    for row in rows:
        enabled = bool(int(row.get("kb_enabled") or 0))
        if not enabled:
            counts["not_added"] += 1
            continue
        counts["kb_enabled"] += 1
        # 状态列缺失（历史行）按「待索引」计，不凭空显示已就绪
        status = row.get("index_status") or "queued"
        if status in counts:
            counts[status] += 1
        counts["chunks"] += int(row.get("chunk_count") or 0)
    return counts


def paper_map(db: MemoryDB, user_id: str) -> dict:
    """paper_id → {id,title,file_name}；供 KB 检索结果回填展示字段。

    Args:
        db: 记忆库连接。
        user_id: 归属用户。

    Returns:
        dict，键为论文 id，值为展示字段。
    """
    rows = db.execute(
        "SELECT id, title, file_name FROM bio_paper WHERE user_id=?",
        (user_id,)).fetchall()
    return {row["id"]: dict(row) for row in rows}
