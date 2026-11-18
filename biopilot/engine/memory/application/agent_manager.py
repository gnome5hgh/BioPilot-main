"""AgentManager：agent 生命周期 + refresh_memory（块变更后重编译 system prompt）。

AgentState 持久化在 bio_agent_state 表——它是一行以 agent_id（即会话 id）为主键的
JSON 快照，其中 message_ids 记录「当前 in-context 窗口的消息 id 列表」。行上带
user_id 做行级隔离，跨用户的会话互不可见。存储经 ``AgentStateRepository`` /
``MessageRepository`` 端口（MySQL 实现在 adapters），本类只做编排：归属防护、
白名单过滤与领域对象组装。
"""
from __future__ import annotations

import json

from biopilot.engine.memory.domain.ports import (
    AgentStateRepository, ConsolidationCursorStore, MemoryBlockReader,
    MessageRepository,
)
from biopilot.engine.memory.domain.schemas.agent import AgentState
from biopilot.engine.memory.domain.schemas.memory import Memory

__all__ = ["AgentManager"]


class AgentManager:
    """agent 生命周期业务层：建/查/改 AgentState，并把块最新状态织入 memory。

    职责：
    1. 管理 bio_agent_state 表（经 ``AgentStateRepository`` 端口）。
    2. 从块表动态构建 AgentState.memory（每轮读取最新块）。
    3. 提供 refresh_memory 钩子供集成层在块变更后重编译 system prompt。

    注意：AgentState.memory 不持久化到 bio_agent_state 表，而是每次 get_agent 时
    通过 MemoryBlockReader 动态生成——保证 memory 始终与块表一致。

    Attributes:
        state: AgentStateRepository，会话状态存储端口
        messages: MessageRepository，消息存储端口（会话列表的消息计数与预览）
        blocks: MemoryBlockReader，块读取端口（动态构建 memory）
        cursors: ConsolidationCursorStore，整合游标（新会话显式建行）
    """

    def __init__(self, state: AgentStateRepository, messages: MessageRepository,
                 blocks: MemoryBlockReader, cursors: ConsolidationCursorStore):
        """初始化 agent 管理器。

        Args:
            state: 会话状态存储端口。
            messages: 消息存储端口（list_sessions 的计数与预览）。
            blocks: 块读取端口（get_agent 时动态读取最新块构建 memory）。
            cursors: 整合游标端口（create_agent 时显式初始化游标行）。
        """
        self.state = state
        self.messages = messages
        self.blocks = blocks
        self.cursors = cursors

    def create_agent(self, agent_id: str, *, user_id: str,
                     name: str | None = None,
                     project_id: str | None = None) -> AgentState:
        """创建 agent（REPLACE INTO 幂等，按主键覆盖），初始 message_ids 为空列表。

        Args:
            agent_id: 唯一标识符。
            user_id: 归属用户（行级隔离的键）。必填——适配层传网关携带的 user_id
                （信任边界：内网带入即真相，引擎不二次鉴权）。
            name: 可选的 agent 名称（可后续更新）。
            project_id: 归属项目（可 None）。

        Returns:
            新建的 AgentState 实例（通过 get_agent 读取）。

        Raises:
            ValueError: user_id 为空。

        幂等性：若 agent_id 已存在，则覆盖（相当于重置）。
        """
        if not user_id:
            raise ValueError("create_agent 需要 user_id（多用户行级隔离的键，缺省即拒绝）")
        # 归属防护：id 已被他人占用时拒绝覆盖（REPLACE 会把他人会话整行抹掉——
        # 窗口 message_ids 清空、user_id 换人）。同用户重复创建=重置语义，照旧放行。
        existing_owner = self.state.owner(agent_id)
        if existing_owner is not None and existing_owner != user_id:
            raise ValueError(f"会话 {agent_id} 已归属其他用户")
        self.state.replace(agent_id, user_id, name, project_id)
        # 新会话从 0 开始消费：游标行必须显式写入，否则整合器会把「行不存在」
        # 当成「历史已消费」而回填到当前消息数，导致第一轮内容永远不进长期记忆。
        # 已有会话的行保持不动（回续语义）。
        self.cursors.ensure(agent_id)
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
        state = self.state.get(agent_id, user_id)
        if state is None:
            raise KeyError(f"agent {agent_id} not found")
        state.memory = Memory(blocks=self.blocks.list_blocks())
        return state

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
            - 本方法不更新 memory，因为 memory 由 get_agent 动态生成。
        """
        allowed = {"name", "description", "system", "model", "context_window_limit",
                   "message_ids"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        # 将 list/dict 序列化为 JSON 字符串以存入数据库（就地写回，值要传给适配层）
        for key, val in updates.items():
            if isinstance(val, (list, dict)):
                updates[key] = json.dumps(val, ensure_ascii=False)
        self.state.update_fields(agent_id, updates)
        return self.get_agent(agent_id)

    def refresh_memory(self, agent_id: str) -> None:
        """从块表重新织入 memory（供 agent 集成作为 system 重编译的挂点）。

        当前 memory 由 get_agent 动态构建（从块表读最新块），因此这里的重赋值只
        作用于局部变量；真实的重编译逻辑在 agent 集成层接入。

        设计意图：
            - 当块表发生变化（如通过 BlockManager 更新）后，集成层可调用此方法
              触发 memory 刷新，随后重新编译 system prompt。
            - 由于 AgentState 是值对象，此方法仅用于显式标记“需要刷新”，实际
              重编译由外部调用者（如 Agent 循环）根据新 state 执行。

        Args:
            agent_id: str，目标会话的 agent 标识
        """
        st = self.get_agent(agent_id)
        st.memory = Memory(blocks=self.blocks.list_blocks())

    def list_sessions(self, limit: int = 10, *, user_id: str,
                      project_id: str | None = None) -> list[dict]:
        """列出该用户的历史会话（新→旧），供会话恢复菜单展示。

        Args:
            limit: 最多返回的会话数。
            user_id: 归属用户过滤（行级隔离；跨用户的会话不出现在结果里）。
            project_id: 项目过滤（None 不过滤）。

        Returns:
            dict 列表，每项含 agent_id / created_at / message_count / preview。

        说明：逐会话查询消息表（每用户会话数有限，无需 JOIN）。
        """
        sessions = []
        for r in self.state.list_session_rows(user_id, limit, project_id):
            agent_id = r["agent_id"]
            first_user = self.messages.first_user_content(agent_id)
            preview = ""
            if first_user:
                preview = str(first_user).strip().replace("\n", " ")[:60]
            sessions.append({
                "agent_id": agent_id,
                "created_at": r["created_at"],
                "message_count": self.messages.count(agent_id),
                "preview": preview,
            })
        return sessions
