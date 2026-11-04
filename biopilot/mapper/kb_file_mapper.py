"""``bio_file`` 中 paper 行的只读 SQL（写者只有 Java）。"""
from __future__ import annotations


def select_papers_for_reconcile(db, user_id: str):
    """取对账所需的论文状态列。"""
    return db.execute(
        "SELECT id, kb_enabled, index_status, chunk_count FROM bio_file"
        " WHERE kind='paper' AND user_id=?", (user_id,)).fetchall()


def select_papers_for_index(db, user_id: str):
    """取索引所需的论文行（含 OSS 键与标题）。"""
    return db.execute(
        "SELECT id, oss_key, kb_enabled, index_status, title FROM bio_file"
        " WHERE kind='paper' AND user_id=?", (user_id,)).fetchall()


def select_paper_states(db, user_id: str):
    """取论文 id 与是否加入知识库。"""
    return db.execute(
        "SELECT id, kb_enabled FROM bio_file WHERE kind='paper' AND user_id=?",
        (user_id,)).fetchall()


def select_all_papers(db):
    """取全量 paper 状态列（启动/周期对账用）。"""
    return db.execute(
        "SELECT user_id, id, kb_enabled, indexed, index_status, index_error,"
        " indexed_at, chunk_count FROM bio_file WHERE kind='paper'"
    ).fetchall()


def select_users_with_kb(db):
    """列出知识库里还有勾选论文的用户。"""
    return db.execute(
        "SELECT DISTINCT user_id FROM bio_file"
        " WHERE kind='paper' AND kb_enabled=1").fetchall()
