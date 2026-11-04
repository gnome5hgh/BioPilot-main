"""附件解析与历史展示服务接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AttachmentService(ABC):
    """把消息体里的附件引用落成本地副本并回填展示元数据。"""

    @abstractmethod
    def resolve(self, user_id: str, attachments: list[dict],
                conversation_id: str) -> list[dict]:
        """取回附件字节并落到用户缓存目录。"""

    @abstractmethod
    def meta(self, attachments: list[dict]) -> list[dict]:
        """从解析结果里取展示用元数据。"""

    @abstractmethod
    def persist(self, user_id: str, conversation_id: str, task: str,
                attachments: list[dict]) -> None:
        """把本轮附件元数据回填到用户消息行。"""

    @abstractmethod
    def display_task(self, content: str) -> str:
        """剥掉注入的附件清单块，只留用户原话。"""
