"""RAG 索引状态的持久化：每个用户域一行，存配方指纹与「文档标识 → 指纹」清单。

索引状态落在 MySQL 的 ``bio_rag_index_state`` 表，而不是工作区文件：运行数据根
随时可能被清空或重定向，增量依据不该跟着丢；多进程同时索引同一域时，文件的
读—改—写也没有可用的互斥手段。读—改—写在持锁事务里完成，同一域的写入串行化。

状态值统一保持数值形状：平台论文没有文件，存内容摘要派生的数值指纹；历史本地
文档的 mtime 浮点数也仍按数值比对（外部评测脚本依赖这一点做增量）。

没有数据库的宿主（单测、嵌入式调用）用 ``MemoryIndexStateStore``：语义一致，只在
进程内生效。写状态失败只告警——状态是增量优化的依据，丢了最多让下次全量重扫，
不该让本次索引失败。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable

__all__ = ["IndexStateStore", "MemoryIndexStateStore", "list_domain_states"]

logger = logging.getLogger(__name__)


class IndexStateStore:
    """MySQL 里的索引状态（每用户域一行）。

    Attributes:
        user_domain: str，归属用户域（``local`` 或登录用户 id）。
        _db: MemoryDB，连接池。
    """

    def __init__(self, db, user_domain: str):
        """绑定连接池与用户域。

        Args:
            db: MemoryDB 实例（提供 execute/transaction）。
            user_domain: 归属用户域。
        """
        self._db = db
        self.user_domain = user_domain or "local"

    def read(self) -> tuple[object, dict] | None:
        """读原始状态，返回 (配方指纹, 文档清单)。

        返回值不做版本判断——版本门控由调用方决定（全量扫描遇到不符配方时全量
        重扫）。记录不存在、SQL 不可达或 JSON 损坏一律返回 None，等同「状态缺失」，
        绝不让坏状态炸掉索引。

        Returns:
            tuple[object, dict] | None: (recipe, {文档标识: 指纹})；无记录时 None。
        """
        try:
            row = self._db.execute(
                "SELECT recipe, state_json FROM bio_rag_index_state"
                " WHERE user_domain=?", (self.user_domain,)).fetchone()
        except Exception as e:
            logger.warning("读取索引状态失败（%s），按状态缺失处理：%s",
                           self.user_domain, e)
            return None
        if not row:
            return None
        try:
            docs = json.loads(row.get("state_json") or "{}")
        except (TypeError, ValueError):
            return None
        if not isinstance(docs, dict):
            return None
        return row.get("recipe") or 0, docs

    def write(self, recipe: object, docs: dict) -> None:
        """整份覆盖该域的状态（全量收敛用）。

        Args:
            recipe: 配方指纹。
            docs: 文档标识 → 指纹 的映射。
        """
        self.mutate(lambda _current: (recipe, docs))

    def clear(self) -> None:
        """删掉该域的状态记录（评测重建、强制全量重扫时用）。

        与「写一份空清单」的区别：空清单仍带配方，会被当成「状态正常、只是没有
        文档」，随后走元数据恢复；删记录才等价于「从未建过索引」。
        """
        try:
            self._db.execute(
                "DELETE FROM bio_rag_index_state WHERE user_domain=?",
                (self.user_domain,))
        except Exception as e:
            logger.warning("清除索引状态失败（%s）：%s", self.user_domain, e)

    def mutate(self, change: Callable[[tuple[object, dict] | None],
                                      tuple[object, dict] | None]) -> None:
        """在持锁事务里读—改—写状态。

        行锁保证并发写同一域时不会「读旧值 → 各自加一项 → 后写覆盖先写」。
        首次写入前先插一条空行占位：``SELECT … FOR UPDATE`` 在行不存在时锁不到
        任何东西，两个并发写者会在主键上相撞、后一个的更新被静默丢弃；占位行把
        首次写入也变成「先锁后改」。回调返回 None 表示不改写（例如旧配方状态要
        留给全量扫描做清理依据）。

        Args:
            change: 接收当前 ``(recipe, docs) | None``，返回要写入的值或 None。
        """
        try:
            with self._db.transaction():
                # 先锁已存在的行；首次写入时行还不存在，FOR UPDATE 锁不到任何东西，
                # 两个并发写者会在主键上相撞、后一个的更新被静默丢弃。没有行就先补
                # 一条占位行（recipe 空串=「还没有配方」）再锁一次，把首次写入也变成
                # 「先锁后改」；后到的写者会在第二次 SELECT 上排队到前者提交。
                row = self._db.execute(
                    "SELECT recipe FROM bio_rag_index_state"
                    " WHERE user_domain=? FOR UPDATE", (self.user_domain,)).fetchone()
                if row is None:
                    self._db.execute(
                        "INSERT IGNORE INTO bio_rag_index_state"
                        " (user_domain, recipe, state_json, updated_at)"
                        " VALUES (?,?,?,?)",
                        (self.user_domain, "", "{}",
                         datetime.now(timezone.utc).isoformat()))
                    row = self._db.execute(
                        "SELECT recipe FROM bio_rag_index_state"
                        " WHERE user_domain=? FOR UPDATE",
                        (self.user_domain,)).fetchone()
                # 占位行对回调呈现为「状态缺失」；真实状态照常读到。
                current = self.read()
                if current is not None and str(current[0] or "") == "":
                    current = None
                result = change(current)
                if result is None:
                    if not row or str(row.get("recipe") or "") == "":
                        self._db.execute(
                            "DELETE FROM bio_rag_index_state WHERE user_domain=?",
                            (self.user_domain,))
                    return
                recipe, docs = result
                self._db.execute(
                    "UPDATE bio_rag_index_state"
                    " SET recipe=?, state_json=?, updated_at=?"
                    " WHERE user_domain=?",
                    (str(recipe), json.dumps(docs, ensure_ascii=False),
                     datetime.now(timezone.utc).isoformat(), self.user_domain))
        except Exception as e:
            # 状态写不进去会让下次全量重扫（正确但更慢），不该让本次索引失败
            logger.warning("写入索引状态失败（%s）：%s", self.user_domain, e)


class MemoryIndexStateStore:
    """进程内索引状态（测试与不接库的宿主用），语义与 MySQL 版一致。

    Attributes:
        _state: tuple[object, dict] | None，当前状态。
        _lock: threading.RLock，保护读—改—写。
    """

    def __init__(self):
        """初始化空状态。"""
        self._lock = threading.RLock()
        self._state: tuple[object, dict] | None = None

    def read(self) -> tuple[object, dict] | None:
        """读原始状态（返回副本，调用方改动不污染内部状态）。"""
        with self._lock:
            if self._state is None:
                return None
            return self._state[0], dict(self._state[1])

    def write(self, recipe: object, docs: dict) -> None:
        """整份覆盖状态。"""
        with self._lock:
            self._state = (recipe, dict(docs))

    def clear(self) -> None:
        """删掉状态（等价于「从未建过索引」）。"""
        with self._lock:
            self._state = None

    def mutate(self, change: Callable[[tuple[object, dict] | None],
                                      tuple[object, dict] | None]) -> None:
        """读—改—写（进程内持锁）。"""
        with self._lock:
            result = change(self.read())
            if result is not None:
                self._state = (result[0], dict(result[1]))


def list_domain_states(db) -> dict[str, dict]:
    """读出所有非 local 域的文档清单（周期对账找孤儿索引用）。

    Args:
        db: MemoryDB 实例。

    Returns:
        dict[str, dict]: 用户域 → {文档标识: 指纹}；读取失败时为空字典。
    """
    try:
        rows = db.execute(
            "SELECT user_domain, state_json FROM bio_rag_index_state"
            " WHERE user_domain <> 'local'").fetchall()
    except Exception as e:
        logger.warning("读取全部索引状态失败：%s", e)
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        try:
            docs = json.loads(row.get("state_json") or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(docs, dict):
            out[str(row["user_domain"])] = docs
    return out
