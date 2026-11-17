"""Agent 域的端口定义（领域层）：会话运行互斥的契约。

对应三层架构方法论中「跨进程互斥只认 MySQL 锁」的硬红线——run() 需要
``run:{conversation_id}`` 命名锁串行化同会话并发，但 Agent（应用层）不该知道
锁的实现（MySQL GET_LOCK 的适配器在 ``memory/adapters/named_lock.py``）。
组装根构造具体锁注入；未注入时 Agent 走降级路径（无锁执行并告警），行为与
历史一致。
"""
from typing import Protocol

__all__ = ["RunMutex"]


class RunMutex(Protocol):
    """跨进程命名互斥锁契约（失败降级语义由调用方承担）。"""

    def acquire(self, name: str, timeout: int) -> bool:
        """尝试获取命名锁（非阻塞语义由实现约定，0 = 立即返回）。

        Args:
            name: 锁名（如 ``run:<conversation_id>``）。
            timeout: 等待秒数；0 表示拿不到立即失败。

        Returns:
            bool: 是否获取成功。
        """
        ...

    def release(self, name: str) -> None:
        """释放命名锁（连接断开时由 MySQL 自愈）。

        Args:
            name: 锁名。
        """
        ...
