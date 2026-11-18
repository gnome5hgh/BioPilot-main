"""引擎侧用户数据两阶段清理实现。"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from biopilot.common.utils.paths import safe_component
from biopilot.service.runtime_state import RuntimeState
from biopilot.engine.memory.adapters.api import (
    delete_consolidation_cursor,
    mark_user_deleting,
    purge_user,
)
from biopilot.mapper import rag_index_mapper, rag_paper_status_mapper
from biopilot.service import state
from biopilot.service.user_service import UserService

logger = logging.getLogger(__name__)


class UserServiceImpl(UserService):
    """删户标记与物理清理。"""

    def __init__(self, runtime: RuntimeState):
        self._runtime = runtime

    def mark_deleting(self, target_id: str) -> dict:
        """删户第一阶段：把 agent_state 归属改名为 deleting:<uid>。"""
        mark_user_deleting(target_id)
        return {"status": "marked"}

    def purge(self, target_id: str) -> dict:
        """物理清除该用户的全部引擎数据（幂等，可重复执行）。"""
        # 记忆域数据（消息/块/历史/游标/状态行）由 memory 适配层一次性清理
        purge_user(target_id)
        try:
            delete_consolidation_cursor(target_id)
        except Exception:
            logger.warning("删户清理跳过 bio_memory_consolidation_cursor")
        try:
            rag_index_mapper.delete_by_user(target_id)
        except Exception:
            logger.warning("删户清理跳过 bio_rag_index_state（表不存在或不可达）")
        try:
            rag_paper_status_mapper.delete_by_user(target_id)
        except Exception:
            logger.warning("删户清理跳过 bio_rag_paper_status（表不存在或不可达）")

        # 向量库按用户域独立 collection：不清会让重建后的同 id 账号检索到旧数据。
        # 适配器实现细节（pymilvus 客户端的构造与关闭）收口在 rag adapters。
        try:
            from biopilot.config import BioPilotConfig
            from biopilot.engine.rag.adapters.vector_store import purge_user_vectors
            purge_user_vectors(BioPilotConfig.from_env(), target_id)
        except Exception as exc:
            logger.warning("删户清理向量库失败（跳过）：%r", exc)

        # 用户派生缓存（附件副本、技能物化）：不属于平台表，但同样含用户数据
        try:
            from biopilot.config import BioPilotConfig, user_cache_root
            cache_dir = (Path(user_cache_root(BioPilotConfig.from_env()))
                         / safe_component(target_id))
            shutil.rmtree(cache_dir, ignore_errors=True)
        except Exception as exc:
            logger.warning("删户清理用户缓存失败（跳过）：%r", exc)

        # 进程内缓存同步丢弃
        for key in [k for k in self._runtime.agents if k[0] == target_id]:
            self._runtime.agents.pop(key, None)
            self._runtime.agent_last_used.pop(key, None)
        for key in [k for k in state._queues if k[0] == target_id]:
            state._queues.pop(key, None)
        state.user_models.pop(target_id, None)
        self._runtime.user_runs.pop(target_id, None)
        self._runtime.usage_baseline.clear()
        return {"status": "purged", "user_id": target_id}
