"""``bio_rag_paper_status`` 的请求级数据访问（委托层）。

SQL 与状态机操作都在 rag 模块的适配层（``engine/rag/adapters/paper_status.py``，
唯一落点）；本模块只保留 service 侧的访问点名，逐条委托——引擎表不再有第二份 SQL。
"""
from __future__ import annotations

from biopilot.engine.rag.adapters import paper_status as _status
from biopilot.mapper.base import shared_db


def select_for_reconcile(user_id: str):
    """取对账所需的论文行：勾选 + 当前索引状态 + 块数。"""
    return _status.select_for_reconcile(shared_db(), user_id)


def select_papers_for_index(user_id: str):
    """取索引所需的论文行（含 OSS 键与标题）。"""
    return _status.select_papers_for_index(shared_db(), user_id)


def select_paper_states(user_id: str):
    """取论文 id 与是否加入知识库（清理已移出论文用）。"""
    return _status.select_paper_states(shared_db(), user_id)


def select_all_papers():
    """取全量论文的勾选与状态（启动/周期对账用，跨用户）。"""
    return _status.select_all_papers(shared_db())


def select_users_with_kb():
    """列出知识库里还有勾选论文的用户（启动对账用）。"""
    return _status.select_users_with_kb(shared_db())


def select_users_with_orphan_rows():
    """列出状态行指向已删除论文的用户（孤儿行要靠下一轮 normalize 清掉）。"""
    return _status.select_users_with_orphan_rows(shared_db())


def normalize(user_id: str, *, requeue_indexing: bool) -> dict:
    """把状态行收敛到勾选真相，返回各步影响行数。"""
    return _status.normalize(shared_db(), user_id, requeue_indexing=requeue_indexing)


def mark_indexing(user_id: str, paper_ids: list[str]) -> list[str]:
    """把仍勾选的论文置为「索引中」，返回被接受的论文 id。"""
    return _status.mark_indexing(shared_db(), user_id, paper_ids)


def apply_results(user_id: str, results: list[dict]) -> dict:
    """批量写入索引结果，返回每篇是否真正落盘。"""
    return _status.apply_results(shared_db(), user_id, results)


def requeue_all(user_id: str) -> int:
    """把该用户所有已勾选论文重排为 queued（强制重建）。"""
    return _status.requeue_all(shared_db(), user_id)


def requeue(user_id: str, paper_ids: list[str]) -> int:
    """把指定论文重排为 queued（失败重试与标题变更重建共用）。"""
    return _status.requeue(shared_db(), user_id, paper_ids)


def delete_by_user(user_id: str):
    """删除某用户的全部状态行（删户清理）。"""
    return _status.delete_by_user(shared_db(), user_id)
