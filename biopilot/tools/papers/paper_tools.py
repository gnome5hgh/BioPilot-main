"""用户论文目录的 HTTP 侧数据访问（供 SpringBoot 代理调用的 Python 内部 API）。

论文原文存 MinIO（users/<uid>/papers/ 前缀），元数据行在 papers 表；RAG 索引
从这些元数据行拉取（工单 17 的输入）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from biopilot.core.memory.storage.database import MemoryDB

__all__ = ["register_paper", "list_papers", "remove_paper"]


def _now() -> str:
    """当前 UTC ISO 时间串。"""
    return datetime.now(timezone.utc).isoformat()


def register_paper(db: MemoryDB, user_id: str, paper_id: str, title: str,
                   oss_key: str, size_bytes: int) -> None:
    """登记一篇已上传到 OSS 的论文元数据行（对象由上传方先行落 OSS）。

    Args:
        db: 记忆库连接（与 Python 其他表同实例）。
        user_id: 归属用户。
        paper_id: 论文唯一标识。
        title: 论文标题（解析器出口；取不到为空串，宁空勿错）。
        oss_key: MinIO 对象键（users/<uid>/papers/... 前缀）。
        size_bytes: 文件大小（字节）。
    """
    db.execute(
        "INSERT INTO papers (id, user_id, title, oss_key, size_bytes, indexed,"
        " created_at) VALUES (?,?,?,?,?,?,?)",
        (paper_id, user_id, title, oss_key, size_bytes, 0, _now()))


def list_papers(db: MemoryDB, user_id: str) -> list[dict]:
    """列出该用户的论文元数据（新→旧）。"""
    rows = db.execute(
        "SELECT id, title, oss_key, size_bytes, indexed, created_at"
        " FROM papers WHERE user_id=? ORDER BY seq DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def remove_paper(db: MemoryDB, user_id: str, paper_id: str) -> str | None:
    """删除论文：先删行（元数据），返回 oss_key 供调用方删对象（删除方向：行→对象）。"""
    row = db.execute("SELECT oss_key FROM papers WHERE id=? AND user_id=?",
                     (paper_id, user_id)).fetchone()
    if row is None:
        return None
    db.execute("DELETE FROM papers WHERE id=? AND user_id=?", (paper_id, user_id))
    return row["oss_key"]
