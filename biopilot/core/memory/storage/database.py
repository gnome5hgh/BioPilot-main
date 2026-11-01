"""MySQL 连接与建表（PyMySQL，连接池）。

多用户真相源（与 server 侧业务表同一 MySQL 实例）：读写走小型连接池，每个操作
借还连接；「读旧值 → 算新值 → 写回」的原子序列走 transaction()——它把一条连接
钉在本线程，事务内所有语句共用该连接，退出时统一 commit / rollback。行级并发
正确性由 InnoDB 行锁承担：块管理器的读-改-写在事务内用 SELECT ... FOR UPDATE
锁行，CAS（WHERE version=?）兜底防绕过入口的写者。

适配约定（让 ORM 层的 SQLite 血统 SQL 少改）：
    - execute/executemany 把 `?` 占位符透明转换为 PyMySQL 的 `%s`。
    - 连接用 DictCursor，查询结果是 dict，`row["col"]` 与 `dict(row)` 都成立。
    - 插入顺序用每表自增 `seq` 列表达（MySQL 没有 rowid）。

Schema 变更约定：建表用 CREATE TABLE IF NOT EXISTS（幂等）；给**已有表**加列
必须登记 _ADDITIVE_COLUMNS，init_schema 每次构建时比对 information_schema 补齐。
"""

from __future__ import annotations

import os
import queue
import threading
from contextlib import contextmanager
from urllib.parse import urlparse

import pymysql
import pymysql.cursors

__all__ = ["MemoryDB"]

# ============================================================================
# 数据库 Schema 定义（幂等建表）
# ============================================================================
_SCHEMA = """
-- blocks 表：核心记忆块存储（业务主表）
CREATE TABLE IF NOT EXISTS blocks (
    id VARCHAR(64) NOT NULL,            -- 块唯一标识
    user_id VARCHAR(191) NOT NULL DEFAULT 'local', -- 归属用户（行级隔离）
    label VARCHAR(191) NOT NULL,        -- 业务标签（如 "assistant", "profile"）
    value MEDIUMTEXT NOT NULL,          -- 块内容（文本）
    `limit` INTEGER NOT NULL DEFAULT 2000, -- 字符长度上限
    description TEXT NULL,              -- 可读描述
    metadata_ TEXT NULL,                -- 扩展元数据（JSON 字符串）
    read_only INTEGER NOT NULL DEFAULT 0, -- 只读标志（0=可写，1=只读）
    version INTEGER NOT NULL DEFAULT 1,   -- 乐观锁版本号（单调递增）
    created_at VARCHAR(40) NOT NULL,    -- 创建时间（ISO 字符串，字典序即可比较）
    updated_at VARCHAR(40) NOT NULL,    -- 最后更新时间（ISO 字符串）
    seq BIGINT NOT NULL AUTO_INCREMENT, -- 插入序（替代 SQLite rowid）
    PRIMARY KEY (id),
    UNIQUE KEY uk_blocks_seq (seq),
    KEY idx_blocks_label (label)
);

-- block_history 表：块历史快照（撤销/重做链）
CREATE TABLE IF NOT EXISTS block_history (
    id BIGINT NOT NULL AUTO_INCREMENT,  -- 自增主键（排序依据）
    user_id VARCHAR(191) NOT NULL DEFAULT 'local', -- 归属用户（行级隔离）
    block_id VARCHAR(64) NOT NULL,      -- 对应的块 ID
    label VARCHAR(191) NOT NULL,        -- 快照时的标签
    value MEDIUMTEXT NOT NULL,          -- 快照时的内容
    `limit` INTEGER NOT NULL,           -- 快照时的字符上限
    description TEXT NULL,              -- 快照时的描述
    metadata_ TEXT NULL,                -- 快照时的元数据（JSON）
    version INTEGER NOT NULL,           -- 快照时的版本号
    checkpointed_at VARCHAR(40) NOT NULL, -- 快照创建时间
    PRIMARY KEY (id),
    KEY idx_block_history_block (block_id)
);

-- consolidation_cursor 表：整合消费权游标（跨进程认领；行存在即已消费到该位置）
-- 行存在即「该 agent 已消费到 cursor 条」；行不存在时按 messages 行数初次回填。
CREATE TABLE IF NOT EXISTS consolidation_cursor (
    agent_id VARCHAR(191) NOT NULL,     -- 归属 agent（主键，与 messages.agent_id 同宽）
    `cursor` BIGINT NOT NULL,           -- 已消费的消息数游标
    updated_at VARCHAR(40) NOT NULL,    -- 最近推进时间
    PRIMARY KEY (agent_id)
);

-- audit_event 表：安全审计事件（insert-only；核心列供查询，payload 存全量取证）
CREATE TABLE IF NOT EXISTS audit_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(191) NULL,
    event_type VARCHAR(40) NOT NULL,
    span_id VARCHAR(32) NULL,
    trace_id VARCHAR(64) NULL,
    session_id VARCHAR(191) NULL,
    agent_type VARCHAR(64) NULL,
    tool_name VARCHAR(191) NULL,
    risk_level VARCHAR(20) NULL,
    turn INTEGER NULL,
    started_at VARCHAR(40) NULL,
    ended_at VARCHAR(40) NULL,
    policy_decision VARCHAR(40) NULL,
    result_status VARCHAR(40) NULL,
    approval_outcome VARCHAR(40) NULL,
    created_at VARCHAR(40) NOT NULL,
    payload MEDIUMTEXT NOT NULL,
    PRIMARY KEY (id),
    KEY idx_audit_trace (trace_id),
    KEY idx_audit_session (session_id, created_at),
    KEY idx_audit_user (user_id, created_at)
);
-- scheduled_task 表：定时任务（webapi 进程内调度器消费；REPL 不跑调度）
CREATE TABLE IF NOT EXISTS scheduled_task (
    id VARCHAR(64) NOT NULL,
    user_id VARCHAR(191) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    task TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    last_run_at VARCHAR(40) NULL,
    next_run_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_sched_user (user_id),
    KEY idx_sched_next (next_run_at)
);

-- papers 表：用户论文目录元数据（原文在 MinIO users/<uid>/papers/，行级 user_id 隔离）
CREATE TABLE IF NOT EXISTS papers (
    id VARCHAR(64) NOT NULL,             -- 论文唯一标识
    user_id VARCHAR(191) NOT NULL,       -- 归属用户
    title VARCHAR(500) NOT NULL,         -- 标题（解析器出口；宁空勿错）
    oss_key VARCHAR(500) NOT NULL,       -- MinIO 对象键
    size_bytes BIGINT NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0,  -- RAG 索引状态（0=未索引）
    created_at VARCHAR(40) NOT NULL,
    seq BIGINT NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_papers_seq (seq),
    KEY idx_papers_user (user_id)
);

-- documents 表：文档编辑器产物（markdown 存 OSS，内容在行内 TEXT）
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(64) NOT NULL,
    user_id VARCHAR(191) NOT NULL,
    name VARCHAR(200) NOT NULL,
    content MEDIUMTEXT NULL,
    oss_key VARCHAR(500) NULL,
    updated_at VARCHAR(40) NOT NULL,
    seq BIGINT NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_documents_seq (seq),
    KEY idx_documents_user (user_id)
);

-- messages 表：对话消息持久化
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(64) NOT NULL,             -- 消息唯一标识
    user_id VARCHAR(191) NOT NULL DEFAULT 'local', -- 归属用户（行级隔离）
    agent_id VARCHAR(191) NOT NULL,      -- 所属 agent（具体对话）
    session_id VARCHAR(191) NULL,        -- 会话分组（同一会话的 supervisor 与子 agent）
    role VARCHAR(20) NOT NULL,           -- system/user/assistant/tool
    content MEDIUMTEXT NULL,             -- 消息内容（纯文本，可为 NULL）
    tool_calls MEDIUMTEXT NULL,          -- 工具调用列表（JSON 数组）
    tool_call_id VARCHAR(64) NULL,       -- 工具调用 ID（关联 tool 消息）
    step_id VARCHAR(64) NULL,            -- 工作流步骤标识
    run_id VARCHAR(64) NULL,             -- 运行标识
    otid VARCHAR(64) NULL,               -- 开放追踪 ID
    meta MEDIUMTEXT NULL,                -- 响应信封（JSON：结束原因/token 用量/模型快照/思维链等）
    created_at VARCHAR(40) NOT NULL,     -- 创建时间
    seq BIGINT NOT NULL AUTO_INCREMENT,  -- 插入序（替代 SQLite rowid）
    PRIMARY KEY (id),
    UNIQUE KEY uk_messages_seq (seq),
    KEY idx_messages_agent (agent_id, created_at),
    KEY idx_messages_session (session_id, created_at)
);
"""

# 增量列迁移清单：(表, 列名, 列定义)。建表脚本只能建出新库——已有库不会因为
# _SCHEMA 多写一列就自动获得它，故给已有表**加列**时必须同时在这里登记一行，
# init_schema 会按它比对 information_schema 并补齐。messages 只增不改，历史行新列为 NULL。
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("messages", "meta", "meta MEDIUMTEXT NULL"),
    ("messages", "session_id", "session_id VARCHAR(191) NULL"),
    # user_id：多用户行级隔离。存量行（单用户时代）落 'local'。
    ("messages", "user_id", "user_id VARCHAR(191) NOT NULL DEFAULT 'local'"),
    ("blocks", "user_id", "user_id VARCHAR(191) NOT NULL DEFAULT 'local'"),
    ("block_history", "user_id", "user_id VARCHAR(191) NOT NULL DEFAULT 'local'"),
    # agent_state 由 AgentManager 自建（不在 _SCHEMA 管辖）；此处登记使存量库在
    # init_schema 时机补列——表尚未建时跳过，建表语句对新库自带该列。
    ("agent_state", "user_id", "user_id VARCHAR(191) NOT NULL DEFAULT 'local'"),
    ("agent_state", "project_id", "project_id VARCHAR(64) NULL"),
)

#: 连接池上限：覆盖「多线程子 agent 并发写记忆 + 事务钉住」的常规并发量。
_POOL_SIZE = 8


def _parse_dsn(dsn: str) -> dict:
    """把 `mysql://user:password@host:port/dbname` 解析成 PyMySQL 连接参数。

    Args:
        dsn: DSN 字符串；密码可为空，库名不能省。

    Returns:
        pymysql.connect 的关键字参数字典（charset 固定 utf8mb4，DictCursor）。
    """
    u = urlparse(dsn)
    if u.scheme != "mysql" or not u.path.lstrip("/"):
        raise ValueError(f"memory_dsn 必须是 mysql://user:pass@host:port/db 形式：{dsn}")
    return {
        "host": u.hostname or "127.0.0.1",
        "port": u.port or 3306,
        "user": u.username or "root",
        "password": u.password or "",
        "database": u.path.lstrip("/"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


class MemoryDB:
    """MySQL 连接池：建库建表 + 线程安全的事务。

    设计决策：
        - 池中连接各自独立线程使用（PyMySQL 连接非线程安全，借还模型天然串行化单条连接）。
        - transaction() 把一条连接钉在本线程（thread-local），事务内的 execute 全部
          落在同一连接上；嵌套事务共享同一次提交，只有最外层退出才 commit / rollback。
        - 事务外的单条操作借连接执行并立即 commit；查询结果由 PyMySQL 客户端缓冲，
          连接归还后再 fetch 也安全。
        - 行级并发正确性：读-改-写序列在事务内用 SELECT ... FOR UPDATE 锁行（调用方
          职责），CAS 条件更新兜底；不再有进程级全局锁，多用户吞吐不受单库大锁限制。

    Attributes:
        dsn: str，连接串（mysql://user:pass@host:port/db）
        _pool: queue.LifoQueue，空闲连接池（懒建，上限 _POOL_SIZE）
        _pinned: threading.local，事务钉住的连接（含嵌套深度）
        _all_conns: list，池中创建过的全部连接（供测试观测，不做清理）
    """

    def __init__(self, dsn: str | None = None, pool_size: int = _POOL_SIZE):
        """建池：DSN 缺省取环境变量 BIOPILOT_MEMORY_MYSQL_DSN，再缺省取本地默认库。

        Args:
            dsn: 连接串；None 时按 环境变量 → _DEFAULT_DSN 顺序取值。
            pool_size: 连接池上限。

        注意：连接建立后自动执行 init_schema() 建表（幂等），并按
        _ADDITIVE_COLUMNS 补齐已有表的缺列。
        """
        # DSN 优先级：显式参数 → 环境变量（测试/本地覆盖通道）→ 报错。
        # 运行时默认值由 config.runtime.memory_dsn 声明（装配层显式传入），
        # 这里不设默认库，避免与 config 的默认值双写漂移。
        self.dsn = dsn or os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN")
        if not self.dsn:
            raise ValueError(
                "未指定记忆库 DSN：装配层应传 config.runtime.memory_dsn，"
                "或设置环境变量 BIOPILOT_MEMORY_MYSQL_DSN"
                "（形如 mysql://root@127.0.0.1:3306/biopilot）")
        self._kwargs = _parse_dsn(self.dsn)
        self._pool: queue.LifoQueue = queue.LifoQueue()
        self._pool_size = pool_size
        self._created = 0
        self._create_lock = threading.Lock()
        self._pinned = threading.local()
        self.init_schema()

    # ------------------------------------------------------------------ 连接池
    def _new_conn(self):
        return pymysql.connect(**self._kwargs)

    def _checkout(self):
        """借一条连接：优先取池中空闲（先 ping 活性），池空且未满则新建，满了等待。

        Returns:
            可用的 pymysql 连接。
        """
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                with self._create_lock:
                    if self._created < self._pool_size:
                        try:
                            conn = self._new_conn()
                        except Exception:
                            self._created -= 1   # 建连失败必须回退计数，否则池位永久漏掉
                            raise
                        self._created += 1
                        return conn
                conn = self._pool.get(timeout=30)
            try:
                conn.ping(reconnect=False)
                return conn
            except Exception:
                # 死连接（服务重启/超时断开）：丢弃重建
                try:
                    conn.close()
                except Exception:
                    pass
                with self._create_lock:
                    self._created = max(0, self._created - 1)

    def _release(self, conn) -> None:
        # 归还前复位会话状态：上一位借主异常退出可能留下未决事务，直接还池会把
        # 脏状态（未提交的写、行锁）传给下一位借主。PyMySQL 的 rollback 对无事务
        # 连接是廉价 no-op。
        try:
            conn.rollback()
        except Exception:
            pass
        self._pool.put(conn)

    # ------------------------------------------------------------------ schema
    def init_schema(self) -> None:
        """建表（幂等）+ 给已有库补齐缺的增量列。

        注意：新增表/改列定义要同步更新 _SCHEMA；给**已有表**加列还要登记到
        _ADDITIVE_COLUMNS，否则只影响新库，老库缺列会在读写时报 Unknown column。
        """
        conn = self._checkout()
        try:
            with conn.cursor() as cur:
                for stmt in _SCHEMA.split(";"):
                    if stmt.strip():
                        cur.execute(stmt)
                self.migrate_additive_columns(cur)
            conn.commit()
        finally:
            self._release(conn)

    def migrate_additive_columns(self, cur=None) -> None:
        """按 _ADDITIVE_COLUMNS 给已存在的表补列（幂等）。

        只做「加列」这一种变更：列已存在即跳过，可反复执行。表不存在时跳过而非
        建表——建表是 _SCHEMA 的职责。历史行的新列留 NULL，由读取方按缺省值处理。

        Args:
            cur: 游标；缺省时自借连接执行（外部调用方如 AgentManager 直接调用本方法）。
        """
        if cur is None:
            conn = self._checkout()
            try:
                with conn.cursor() as c:
                    self.migrate_additive_columns(c)
                conn.commit()
            finally:
                self._release(conn)
            return
        for table, column, ddl in _ADDITIVE_COLUMNS:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS"
                " WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (self._kwargs["database"], table))
            existing = {r["COLUMN_NAME"] for r in cur.fetchall()}
            if existing and column not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    # ------------------------------------------------------------------ 事务
    def _pinned_conn(self):
        """取本线程事务钉住的连接；不在事务内返回 None。"""
        return getattr(self._pinned, "conn", None)

    @contextmanager
    def transaction(self):
        """把多条语句包成一次原子操作（读-改-写序列必须走这里）。

        连接钉住本线程：事务内所有 execute 落在同一连接；嵌套调用共享同一次
        提交，只有最外层退出时才 commit / rollback。行锁（FOR UPDATE）随事务
        持有到最外层退出，崩溃时随连接归还/断开释放。

        Yields:
            钉住的 pymysql 连接（供需要直接操作的调用方使用）。
        """
        if self._pinned_conn() is not None:
            # 嵌套：复用外层事务
            self._pinned.depth += 1
            try:
                yield self._pinned.conn
            finally:
                self._pinned.depth -= 1
            return
        conn = self._checkout()
        self._pinned.conn = conn
        self._pinned.depth = 1
        try:
            conn.begin()
            yield conn
        except BaseException:
            conn.rollback()
            raise
        else:
            try:
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            self._pinned.conn = None
            self._pinned.depth = 0
            self._release(conn)

    @property
    def _tx_depth(self) -> int:
        """事务嵌套深度（0 = 不在事务内）。兼容旧读取方。"""
        conn = self._pinned_conn()
        return getattr(self._pinned, "depth", 0) if conn is not None else 0

    # ------------------------------------------------------------------ 执行
    @staticmethod
    def _to_mysql(sql: str) -> str:
        """把 SQLite 血统的 `?` 占位符转换为 PyMySQL 的 `%s`。

        约定：本仓 SQL 全部由代码拼装、字符串字面量不含 `?`，整体替换安全。

        Args:
            sql: 原始 SQL。

        Returns:
            占位符已转换的 SQL。
        """
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple = ()):
        """执行单条 SQL；不在事务内时借连接立即 commit（事务内由最外层统一提交）。

        Args:
            sql: SQL 语句（`?` 占位符，内部透明转 `%s`）。
            params: 参数元组，默认为空。

        Returns:
            pymysql 游标（DictCursor，结果可按列名访问），可用于 fetch。

        注意：
            - 事务内使用钉住连接且不提交；事务外借池中连接、执行完立即 commit 并归还。
            - PyMySQL 默认客户端缓冲全部结果行，连接归还后 fetch 仍可用。
        """
        sql = self._to_mysql(sql)
        conn = self._pinned_conn()
        if conn is not None:
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur
        conn = self._checkout()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._pinned_conn() is None:
                self._release(conn)

    def executemany(self, sql: str, seq: list[tuple]) -> None:
        """批量执行；不在事务内时借连接立即 commit（事务内由最外层统一提交）。

        Args:
            sql: SQL 语句（`?` 占位符）。
            seq: 参数元组列表，每个元组对应一次执行。

        注意：失败时整个批量操作回滚（PyMySQL executemany 在单条语句内完成）。
        """
        sql = self._to_mysql(sql)
        conn = self._pinned_conn()
        if conn is not None:
            conn.cursor().executemany(sql, seq)
            return
        conn = self._checkout()
        try:
            conn.cursor().executemany(sql, seq)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release(conn)
