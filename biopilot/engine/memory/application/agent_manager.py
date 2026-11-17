"""AgentManager：agent 生命周期 + refresh_memory（块变更后重编译 system prompt）。

AgentState 持久化在 bio_agent_state 表——它是一行以 agent_id（即会话 id）为主键的
JSON 快照，其中 message_ids 记录「当前 in-context 窗口的消息 id 列表」。行上带
user_id 做行级隔离，跨用户的会话互不可见。SQL 翻译在 ``adapters/agent_state.py``，
本层只做编排：归属防护、白名单过滤与领域对象组装。
"""
from __future__ import annotations

import json

from biopilot.engine.memory.adapters import agent_state as agent_state_store
from biopilot.engine.memory.adapters.database import MemoryDB
from biopilot.engine.memory.domain.schemas.agent import AgentState
from biopilot.engine.memory.domain.schemas.memory import Memory
from biopilot.engine.memory.application.block_manager import BlockManager
from biopilot.engine.memory.application.message_manager import MessageManager

__all__ = ["AgentManager"]


class AgentManager:
    """agent 生命周期业务层：建/查/改 AgentState，并把块最新状态织入 memory。

    职责：
    1. 管理 bio_agent_state 表（经 ``adapters/agent_state.py`` 的 SQL 翻译）。
    2. 从块表动态构建 AgentState.memory（每轮读取最新块）。
    3. 提供 refresh_memory 钩子供集成层在块变更后重编译 system prompt。

    注意：AgentState.memory 不持久化到 bio_agent_state 表，而是每次 get_agent 时
    通过 block_manager.list_blocks() 动态生成——保证 memory 始终与块表一致。

    Attributes:
        db: MemoryDB，bio_agent_state 表的连接
        block_manager: BlockManager，get_agent 时动态读取最新块构建 memory
        message_manager: MessageManager，供后续扩展（当前未使用）
    """

    def __init__(self, db: MemoryDB, block_manager: BlockManager,
                 message_manager: MessageManager):
        """初始化并创建 bio_agent_state 表（若不存在）。

        Args:
            db: 数据库连接。
            block_manager: 块管理器（用于动态读取块列表）。
            message_manager: 消息管理器（供后续扩展，当前未使用）。
        """
        self.db = db
        self.block_manager = block_manager
        self.message_manager = message_manager
        agent_state_store.ensure_table(db)

    def _row_to_state(self, row: dict) -> AgentState:
        """把 DB 行转回 AgentState：memory 从 block_manager 现读最新块动态构建。

        Args:
            row: 数据库行（dict 形式，含 agent_id, name, description, system,
                model, context_window_limit, message_ids, created_at）。

        Returns:
            填充好的 AgentState 实例。

        关键设计：
            - memory 字段不来自 DB，而是通过 block_manager.list_blocks() 实时获取，
              保证了块表变更后立刻反映到 AgentState 中，无需额外刷新。
            - message_ids 从 JSON 字符串还原为列表。
        """
        return AgentState(
            agent_id=row["agent_id"],
            name=row["name"],
            description=row["description"],
            system=row["system"],
            model=row["model"],
            context_window_limit=row["context_window_limit"],
            message_ids=json.loads(row["message_ids"]) if row["message_ids"] else [],
            memory=Memory(blocks=self.block_manager.list_blocks()),
            created_at=row["created_at"],
            user_id=str(row["user_id"]),
            project_id=row.get("project_id"),
        )

    def create_agent(self, agent_id: str, *, user_id: str,
                     name: str | None = None,
                     project_id: str | None = None) -> AgentState:
        """创建 agent（REPLACE INTO 幂等，按主键覆盖），初始 message_ids 为空列表。

        Args:
            agent_id: 唯一标识符。
            user_id: 归属用户（行级隔离的键）。必填——适配层传网关携带的 user_id
                （信任边界：内网带入即真相，引擎不二次鉴权）。
            name: 可选的 agent 名称（可后续更新）。

        Returns:
            新建的 AgentState 实例（通过 get_agent 读取）。

        幂等性：若 agent_id 已存在，则覆盖（相当于重置）。
        """
        if not user_id:
            raise ValueError("create_agent 需要 user_id（多用户行级隔离的键，缺省即拒绝）")
        # 归属防护：id 已被他人占用时拒绝覆盖（REPLACE 会把他人会话整行抹掉——
        # 窗口 message_ids 清空、user_id 换人）。同用户重复创建=重置语义，照旧放行。
        existing_owner = agent_state_store.fetch_owner(self.db, agent_id)
        if existing_owner is not None and existing_owner != user_id:
            raise ValueError(f"会话 {agent_id} 已归属其他用户")
        agent_state_store.replace_row(self.db, agent_id, user_id, name, project_id)
        # 新会话从 0 开始消费：游标行必须显式写入，否则整合器会把「行不存在」
        # 当成「历史已消费」而回填到当前消息数，导致第一轮内容永远不进长期记忆。
        # 已有会话的行保持不动（回续语义）。
        agent_state_store.init_cursor(self.db, agent_id)
        return self.get_agent(agent_id)

    def get_agent(self, agent_id: str, user_id: str | None = None) -> AgentState:
        """按 id 取 AgentState；不存在（或归属不符）抛 KeyError。

        Args:
            agent_id: 要查询的 agent 标识。
            user_id: 归属过滤（传则只返回该用户的会话）——多用户进程里会话 id
                由客户端生成，不做归属校验的话拿到别人的 id 就能读到他人上下文。

        Returns:
            当前最新的 AgentState（memory 动态构建）。

        Raises:
            KeyError: 当 agent_id 不存在或归属不符时（不区分两种情况，避免探针）。
        """
        row = agent_state_store.fetch_row(self.db, agent_id, user_id)
        if row is None:
            raise KeyError(f"agent {agent_id} not found")
        return self._row_to_state(row)

    def update_agent(self, agent_id: str, **kwargs) -> AgentState:
        """局部更新 AgentState 白名单字段（list/dict 自动序列化为 JSON），返回更新后状态。

        Args:
            agent_id: 目标 agent 标识。
            **kwargs: 允许更新的字段，包括 name, description, system, model,
                context_window_limit, message_ids。其中 list/dict
                自动转为 JSON 字符串。

        Returns:
            更新后的 AgentState 实例。

        注意：
            - 仅允许白名单内的字段，其他字段被忽略。
            - 每个字段单独执行 UPDATE，若多次更新不同字段会产生多次 SQL 调用，
              但本方法设计为一次性更新多个字段的便捷入口，调用方应传入完整字段集。
            - 本方法不更新 memory，因为 memory 由 _row_to_state 动态生成。
        """
        allowed = {"name", "description", "system", "model", "context_window_limit",
                   "message_ids"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        # 将 list/dict 序列化为 JSON 字符串以存入数据库（就地写回，值要传给适配层）
        for key, val in updates.items():
            if isinstance(val, (list, dict)):
                updates[key] = json.dumps(val, ensure_ascii=False)
        agent_state_store.update_fields(self.db, agent_id, updates)
        return self.get_agent(agent_id)

    def refresh_memory(self, agent_id: str) -> None:
        """从块表重新织入 memory（供 agent 集成作为 system 重编译的挂点）。

        当前 memory 由 get_agent 动态构建（_row_to_state 从 block_manager
        .list_blocks 读最新块），因此这里的重赋值只作用于局部变量；真实的重
        编译逻辑在 agent 集成层接入。

        设计意图：
            - 当块表发生变化（如通过 BlockManager 更新）后，集成层可调用此方法
              触发 memory 刷新，随后重新编译 system prompt。
            - 由于 AgentState 是值对象，此方法仅用于显式标记“需要刷新”，实际
              重编译由外部调用者（如 Agent 循环）根据新 state 执行。

        Args:
            agent_id: str，目标会话的 agent 标识
        """
        st = self.get_agent(agent_id)
        st.memory = Memory(blocks=self.block_manager.list_blocks())

    def list_sessions(self, limit: int = 10, *, user_id: str,
                      project_id: str | None = None) -> list[dict]:
        """列出该用户的历史会话（新→旧），供会话恢复菜单展示。

        Args:
            limit: 最多返回的会话数。
            user_id: 归属用户过滤（行级隔离；跨用户的会话不出现在结果里）。

        Returns:
            dict 列表，每项含：
                - agent_id: 会话标识（会话列表与恢复的目标 id）
                - created_at: 会话创建时间
                - message_count: 该会话落盘消息总数
                - preview: 首条用户消息的截断预览（无消息则为空串）

        说明：逐会话查询消息表（每用户会话数有限，无需 JOIN）。
        """
        from biopilot.engine.memory.adapters.message import count_messages

        sessions = []
        for r in agent_state_store.list_session_rows(self.db, user_id, limit,
                                                     project_id):
            agent_id = r["agent_id"]
            first_user = agent_state_store.fetch_first_user_content(self.db, agent_id)
            preview = ""
            if first_user:
                preview = str(first_user).strip().replace("\n", " ")[:60]
            sessions.append({
                "agent_id": agent_id,
                "created_at": r["created_at"],
                "message_count": count_messages(self.db, agent_id),
                "preview": preview,
            })
        return sessions
