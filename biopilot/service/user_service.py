"""删户清理服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class UserService(ABC):
    """引擎侧用户数据两阶段清理。"""

    @abstractmethod
    def mark_deleting(self, target_id: str) -> dict:
        """删户第一阶段：标记归属。"""

    @abstractmethod
    def purge(self, target_id: str) -> dict:
        """删户第二阶段：物理清理引擎数据。"""
