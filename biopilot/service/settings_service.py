"""设置页服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SettingsService(ABC):
    """读取有效配置、校验补丁、写入数据库、历史与回滚。"""

    @abstractmethod
    def snapshot(self) -> dict:
        """返回设置页需要的全部数据。"""

    @abstractmethod
    def patch(self, body: dict, updated_by: str) -> dict:
        """校验并写入一批配置补丁。"""

    @abstractmethod
    def history(self, limit: int = 20) -> dict:
        """返回最近的保存历史。"""

    @abstractmethod
    def rollback(self, version: int, updated_by: str) -> dict:
        """回滚到指定历史版本。"""
