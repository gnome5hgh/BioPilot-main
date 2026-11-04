"""模型清单与会话级模型选择服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ModelService(ABC):
    """读取可用模型并维护会话级选择。"""

    @abstractmethod
    def list(self, user_id: str) -> dict:
        """返回主模型 + runtime.models 条目。"""

    @abstractmethod
    def select(self, user_id: str, name: str) -> dict:
        """设置本用户后续 run 使用的模型。"""
