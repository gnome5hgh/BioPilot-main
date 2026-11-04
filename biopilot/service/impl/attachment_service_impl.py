"""附件解析与历史展示实现。"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Callable

from biopilot.common.utils.paths import safe_component
from biopilot.mapper import message_mapper
from biopilot.mapper.base import shared_db
from biopilot.service.attachment_service import AttachmentService
from biopilot.service.config_helpers import cfg_user_cache_root

logger = logging.getLogger(__name__)

#: 附件清单注入任务文本时使用的固定抬头：历史回放据此把注入块从展示正文中剥掉。
ATTACHMENT_HEADER = "【附件】以下数据文件已就位"


class AttachmentServiceImpl(AttachmentService):
    """附件解析、展示元数据与用户消息回填。"""

    def __init__(self, platform_client: Callable | None = None):
        if platform_client is None:
            from biopilot.service.impl.platform_client import shared_platform_client
            platform_client = shared_platform_client
        self._platform_client = platform_client

    def resolve(self, user_id: str, attachments: list[dict],
                conversation_id: str) -> list[dict]:
        """把消息引用的附件落成本地文件并返回清单（发给模型的元数据行）。

        身份与字节都由 Java 解析：这里只传 ``(kind, id)``，拿回字节与服务器侧
        元数据。body 里的 oss_key/name/size 一律忽略——它们来自浏览器，不能作为
        归属依据（否则可以把别人的 oss_key 塞进来读走别人的文件）。

        本地副本落到 ``<用户缓存根>/<uid>/uploads/<会话>/``，沙箱按会话挂载该目录；
        路径片段先归一化，防客户端传入 ``..`` 写出上传目录。

        Args:
            user_id: 归属用户。
            attachments: 消息体里的 {file_id|paper_id, ...} 列表。
            conversation_id: 会话 id（本地副本目录的一部分）。

        Returns:
            list[dict]: [{name, size, path, file_id, paper_id, oss_key}]。
        """
        out: list[dict] = []
        if not attachments:
            return out
        base = (pathlib.Path(cfg_user_cache_root())
                / safe_component(user_id) / "uploads"
                / safe_component(conversation_id))
        for att in attachments:
            att = att or {}
            file_id = str(att.get("file_id") or "")
            paper_id = str(att.get("paper_id") or "")
            if paper_id:
                kind, obj_id = "paper", paper_id
            elif file_id:
                kind, obj_id = "file", file_id
            else:
                continue
            try:
                data, meta = self._platform_client().attachment(
                    user_id, kind, obj_id)
            except Exception as exc:
                logger.warning("附件取回失败（%s=%s）：%s", kind, obj_id, exc)
                continue
            if not data:
                continue
            name = safe_component(meta.get("name") or obj_id)
            target = base / f"{safe_component(obj_id)}_{name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.stat().st_size != len(data):
                target.write_bytes(data)
            out.append({"name": name, "size": meta.get("size") or len(data),
                        "path": str(target), "file_id": file_id or None,
                        "paper_id": paper_id or None,
                        "oss_key": meta.get("oss_key") or ""})
        return out

    def meta(self, attachments: list[dict]) -> list[dict]:
        """从解析结果里取「展示用」附件元数据（历史回放复现文件卡片）。"""
        meta = []
        for att in attachments:
            item = {"name": att.get("name", ""), "size": att.get("size", 0)}
            if att.get("paper_id"):
                item["paper_id"] = att["paper_id"]
            elif att.get("file_id"):
                item["file_id"] = att["file_id"]
            else:
                continue
            if att.get("oss_key"):
                item["oss_key"] = att["oss_key"]
            meta.append(item)
        return meta

    def persist(self, user_id: str, conversation_id: str, task: str,
                attachments: list[dict]) -> None:
        """把本轮附件元数据回填到用户消息行的 meta（历史回放展示用）。"""
        if not attachments:
            return
        prefix = task.split("\n\n", 1)[0] + "\n\n"
        try:
            message_mapper.update_user_message_meta(
                shared_db(), user_id, conversation_id, len(prefix), prefix,
                json.dumps({"attachments": attachments}, ensure_ascii=False))
        except Exception:
            logger.warning("附件元数据回填失败（不影响本轮回答）", exc_info=True)

    def display_task(self, content: str) -> str:
        """剥掉注入的附件清单块，只留用户原话（历史回放展示用）。"""
        if not content or not content.startswith(ATTACHMENT_HEADER):
            return content
        marker = content.find("\n\n")
        return content[marker + 2:] if marker >= 0 else content
