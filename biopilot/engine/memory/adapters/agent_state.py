"""bio_agent_state 表的 SQL 访问（适配层）。

AgentManager（应用层）负责归属防护、白名单与领域对象组装；本模块只做
「领域参数 ⇄ SQL 行」的翻译：幂等建表、行读写、整合游标初始化与会话列表查询。
与 message.py / block.py 同风格——模块级函数、``db`` 由调用方传入。
"""
from __future__ import annotations

from datetime import datetime, timezone

__all__ = [
    "ensure_table", "fetch_owner", "fetch_row", "replace_row", "init_cursor",
    "update_fields", "list_session_rows", "fetch_first_user_content",
]


def ensure_table(db) -> None:
    """幂等建表 bio_agent_state（建表语句只管新库，老库补列走增量迁移）。

    Args:
        db: MemoryDB，连接池（事务/执行入口）。
    """
    # system 是 MySQL 8 保留字，列名一律反引号；agent_id 用 VARCHAR（TEXT 不能作主键）
    db.execute("CREATE TABLE IF NOT EXISTS bio_agent_state ("
               "agent_id VARCHAR(64) PRIMARY KEY, name TEXT, description TEXT,"
               "`system` MEDIUMTEXT, model TEXT, context_window_limit INTEGER,"
               "message_ids MEDIUMTEXT, created_at VARCHAR(40),"
               "user_id VARCHAR(191) NOT NULL,"
               "project_id VARCHAR(64) NULL)")
    db.migrate_additive_columns()


def fetch_owner(db, agent_id: str) -> str | None:
    """读一行当前的归属 user_id；行不存在返回 None。

    Args:
        db: MemoryDB。
        agent_id: 会话标识（表主键）。

    Returns:
        str | None：归属 user_id；无该行时 None。
    """
    row = db.execute("SELECT user_id FROM bio_agent_state WHERE agent_id=?",
                     (agent_id,)).fetchone()
    return None if row is None else row["user_id"]


def fetch_row(db, agent_id: str, user_id: str | None = None) -> dict | None:
    """按 id 取一行（可选归属过滤）；无匹配返回 None。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。
        user_id: 归属过滤（None 不过滤；传入则要求行归属该用户）。

    Returns:
        dict | None：整行（列名 → 值）；无匹配时 None。
    """
    if user_id is None:
        cur = db.execute("SELECT * FROM bio_agent_state WHERE agent_id=?", (agent_id,))
    else:
        cur = db.execute("SELECT * FROM bio_agent_state WHERE agent_id=? AND user_id=?",
                         (agent_id, user_id))
    row = cur.fetchone()
    return None if row is None else dict(row)


def replace_row(db, agent_id: str, user_id: str, name: str | None,
                project_id: str | None) -> None:
    """REPLACE INTO 幂等写入一行（按主键覆盖），初始 message_ids 为空列表。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。
        user_id: 归属用户（行级隔离键）。
        name: 会话名（可 None）。
        project_id: 归属项目（可 None）。
    """
    db.execute(
        "REPLACE INTO bio_agent_state (agent_id, user_id, name, message_ids, created_at,"
        " project_id) VALUES (?,?,?,?,?,?)",
        (agent_id, user_id, name, "[]",
         datetime.now(timezone.utc).isoformat(), project_id))


def init_cursor(db, agent_id: str) -> None:
    """初始化整合游标行为 0（新会话从 0 开始消费；已有行保持不动）。

    Args:
        db: MemoryDB。
        agent_id: 会话标识（游标按 agent_id 键控，无 user_id 维度）。
    """
    db.execute(
        "INSERT IGNORE INTO bio_memory_consolidation_cursor"
        " (agent_id, `cursor`, updated_at) VALUES (?,?,?)",
        (agent_id, 0, datetime.now(timezone.utc).isoformat()))


_UPDATABLE_COLUMNS = frozenset({
    "name", "description", "system", "model", "context_window_limit", "message_ids",
})


def update_fields(db, agent_id: str, updates: dict[str, str]) -> None:
    """按「列名 → 已序列化值」逐列更新一行（键来自应用层白名单）。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。
        updates: 列名 → 值（应用层已把 list/dict 序列化为 JSON 字符串）。

    Raises:
        ValueError: 列名不在本表可更新集合内（适配器侧二次把关，f-string 拼列名
            只接受这份闭集，不信任调用方白名单的跨层纪律）。
    """
    for key, val in updates.items():
        if key not in _UPDATABLE_COLUMNS:
            raise ValueError(f"bio_agent_state 不允许更新列: {key}")
        db.execute(f"UPDATE bio_agent_state SET {key}=? WHERE agent_id=?",
                   (val, agent_id))


def list_session_rows(db, user_id: str, limit: int,
                      project_id: str | None = None) -> list[dict]:
    """列出该用户的会话行（新→旧），可选项目过滤。

    Args:
        db: MemoryDB。
        user_id: 归属用户（行级隔离）。
        limit: 最多返回的会话数。
        project_id: 项目过滤（None 不过滤）。

    Returns:
        dict 列表，每项含 agent_id 与 created_at。
    """
    if project_id is not None:
        rows = db.execute(
            "SELECT agent_id, created_at FROM bio_agent_state"
            " WHERE user_id=? AND project_id=?"
            " ORDER BY created_at DESC, agent_id LIMIT ?", (user_id, project_id, limit)).fetchall()
    else:
        rows = db.execute(
            "SELECT agent_id, created_at FROM bio_agent_state WHERE user_id=?"
            " ORDER BY created_at DESC, agent_id LIMIT ?", (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def fetch_first_user_content(db, agent_id: str) -> str | None:
    """取该会话首条用户消息的 content（会话列表预览用）；无消息返回 None。

    Args:
        db: MemoryDB。
        agent_id: 会话标识。

    Returns:
        str | None：首条用户消息原文；该会话还没有消息时 None。
    """
    row = db.execute(
        "SELECT content FROM bio_message WHERE agent_id=? AND role='user'"
        " ORDER BY created_at, seq LIMIT 1", (agent_id,)).fetchone()
    return None if row is None else row["content"]
