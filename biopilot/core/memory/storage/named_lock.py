"""MySQL 命名锁：跨进程互斥的原语（GET_LOCK 语义）。

GET_LOCK 是连接级锁：同一条连接获取与释放；连接断开（进程崩溃/网络闪断）锁
自动释放——这正是跨进程防护需要的自愈语义，不需要租约心跳。每把锁独占一条
专用连接（不经 MemoryDB 的池，避免长持锁挤占业务连接），用完即关。

超时语义：acquire(timeout=0) 立即返回成功/失败（不等待），调用方据此决定
「放弃本轮」还是「重试」。锁名约定：``run:{conversation_id}``（会话运行互斥）、
``consolidation:{agent_id}``（整合消费权）。
"""
from __future__ import annotations

import pymysql

from biopilot.core.memory.storage.database import _parse_dsn

__all__ = ["NamedLock"]


class NamedLock:
    """基于 MySQL GET_LOCK 的跨进程互斥锁。

    Attributes:
        dsn: str，连接串（mysql://user:pass@host:port/db；锁与库同实例即可，
            不要求库名一致——命名锁是实例级命名空间）
    """

    def __init__(self, dsn: str):
        """记录连接参数（连接在 acquire 时才建立，失败立即暴露）。

        Args:
            dsn: 连接串。
        """
        self.dsn = dsn

    def _connect(self):
        kwargs = dict(_parse_dsn(self.dsn))
        kwargs["database"] = kwargs["database"] or None
        kwargs["autocommit"] = True
        return pymysql.connect(**kwargs)

    def acquire(self, name: str, timeout: int = 0) -> bool:
        """获取命名锁（独占一条专用连接持有它）。

        Args:
            name: 锁名（实例级命名空间内唯一）。
            timeout: 等待秒数；0 表示立即返回。

        Returns:
            True=获取成功；False=已被他人持有。

        Raises:
            pymysql.err.Error: MySQL 不可达等基础设施故障（调用方决定降级策略）。
        """
        if getattr(self, "_conn", None) is not None:
            raise RuntimeError(f"NamedLock 重复 acquire：已持有 {self._name!r}，"
                               "先 release 或换新实例（否则会泄漏首条连接）")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                # GET_LOCK 返回 1=成功 / 0=超时未得 / NULL=出错（如超时为负）
                cur.execute("SELECT GET_LOCK(%s, %s) AS got", (name, timeout))
                got = cur.fetchone()["got"]
        except Exception:
            conn.close()
            raise
        if got == 1:
            self._conn = conn
            self._name = name
            return True
        conn.close()
        if got is None:
            # NULL 不是「锁被占用」：它表示 GET_LOCK 自身出错（参数/权限/服务异常）。
            # 当成竞争会把基础设施故障伪装成正常抢锁失败，让调用方静默跳过本轮工作。
            raise RuntimeError(f"GET_LOCK 返回 NULL（{name}），无法判断锁状态")
        return False

    def release(self, name: str) -> None:
        """释放命名锁并关闭专用连接。

        Args:
            name: 锁名（须与本实例 acquire 的名字一致）。
        """
        conn = getattr(self, "_conn", None)
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT RELEASE_LOCK(%s)", (name,))
        except Exception:
            pass    # 连接已断的场合锁必然已自动释放，无需补救
        finally:
            try:
                conn.close()
            except Exception:
                pass
            self._conn = None
