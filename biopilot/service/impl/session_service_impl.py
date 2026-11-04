"""会话历史、删除与上下文用量实现。"""
from __future__ import annotations

import json
import logging

from biopilot.domain.runtime_state import RuntimeState
from biopilot.mapper import agent_state_mapper, message_mapper
from biopilot.mapper.base import shared_db
from biopilot.service import state
from biopilot.service.attachment_service import AttachmentService
from biopilot.service.errors import NotFoundError, RequestValidationError
from biopilot.service.session_service import SessionService

logger = logging.getLogger(__name__)


class SessionServiceImpl(SessionService):
    """会话级轻量查询与进程内缓存维护。"""

    def __init__(self, runtime: RuntimeState, attachments: AttachmentService):
        self._runtime = runtime
        self._attachments = attachments

    async def autotitle(self, user_id: str, conversation_id: str,
                        task: str) -> None:
        """首条任务生成会话标题：name 为空才设，取任务前 20 字。"""
        try:
            db = shared_db()
            row = agent_state_mapper.select_name(db, conversation_id, user_id)
            if row is not None and row["name"] is None:
                title = task.strip().replace("\n", " ")[:20]
                agent_state_mapper.update_name(db, title, conversation_id, user_id)
        except Exception as e:      # pragma: no cover
            logger.warning("会话标题生成失败: %r", e)

    def history(self, user_id: str, conversation_id: str) -> dict:
        """取一段会话的可见历史（user/assistant 两条腿，按时间正序）。"""
        if not conversation_id:
            return {"messages": []}
        rows = message_mapper.select_history(shared_db(), user_id, conversation_id)
        messages = []
        for row in rows:
            item = {
                "role": row["role"],
                "content": self._attachments.display_task(row["content"]),
                "created_at": row["created_at"],
            }
            if row["role"] == "user" and row["meta"]:
                try:
                    attachments = json.loads(row["meta"]).get("attachments")
                except (ValueError, AttributeError):
                    attachments = None
                if attachments:
                    item["attachments"] = attachments
            messages.append(item)
        return {"messages": messages}

    def delete(self, user_id: str, conversation_id: str) -> dict:
        """删除一个会话：消息行 + agent_state 行（归属双条件）。"""
        if not conversation_id:
            raise RequestValidationError("缺少 conversation_id")
        db = shared_db()
        message_mapper.delete_for_conversation(db, user_id, conversation_id)
        gone = agent_state_mapper.delete_for_conversation(
            db, user_id, conversation_id)
        self._runtime.agents.pop(
            (user_id, conversation_id, state.user_models.get(user_id)), None)
        # 键含模型名（会话内可切换模型），按用户+会话整体清
        for stale in [k for k in self._runtime.agent_last_used
                      if k[0] == user_id and k[1] == conversation_id]:
            self._runtime.agent_last_used.pop(stale, None)
        state._queues.pop((user_id, conversation_id), None)
        if gone == 0:
            raise NotFoundError("会话不存在")
        return {"status": "ok"}

    def context_usage(self, user_id: str, conversation_id: str) -> dict:
        """当前会话的上下文窗口用量分解（head + 工具 schema + 消息）。"""
        if not conversation_id:
            return {"usage": None}
        agent = self._runtime.agents.get(
            (user_id, conversation_id, state.user_models.get(user_id)))
        if agent is not None:
            try:
                return {"usage": agent.context_usage()}
            except Exception:
                logger.warning("上下文用量计算失败", exc_info=True)
        # 未装配路径：基线（head + 工具 schema）+ 消息份（从 DB 逐行估算）
        baseline = self._runtime.usage_baseline.get(
            (user_id, state.user_models.get(user_id)))
        if baseline is None:
            return {"usage": None}
        parts = dict(baseline["parts"])
        try:
            from biopilot.common.utils.tokenization import estimate_text_tokens
            rows = message_mapper.select_context_rows(
                shared_db(), user_id, conversation_id)
            msg_tokens = 0
            for r in rows:
                text = f"{r['role']}: {r['content'] or ''}"
                if r["tool_calls"]:
                    text += r["tool_calls"]
                msg_tokens += estimate_text_tokens(text) + 4
            parts["messages"] = msg_tokens
        except Exception:
            parts["messages"] = 0
        return {"usage": {"total": sum(parts.values()),
                          "limit": baseline["limit"], "parts": parts}}

    def invalidate_agents(self) -> None:
        """丢弃全部缓存的 Agent：设置保存后下一轮按新配置重新装配。"""
        self._runtime.agents.clear()
        self._runtime.agent_last_used.clear()
        self._runtime.usage_baseline.clear()
