"""用户数据文件的 OSS 存取（pool 模式：共享桶 + users/<uid>/ 前缀）。

平台所有用户产生的数据文件（文档成稿、分析脚本与产物、上传的数据集等）
统一收进对象存储：键以 ``users/<uid>/files/<类别>/<路径>`` 起——与论文原图、
工具结果外置同一桶、同一前缀约定。MinIO 不可达时回退本地
``<workspace>/user-files/<同键>``（键在两种形态下保持一致，调用方无感）。

这是纯存取器：不做归属校验（调用方拿到的 user_id 即信任边界内的真相），
不做格式解释（字节进出）。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: 连接失败后的冷却时间（秒）：与图表原图存取器同一思路，避免按文件重复等超时
_FAILURE_COOLDOWN = 60.0


def _safe_component(component: str) -> str:
    """把路径段收敛成对象键安全片段（剥分隔符与控制字符，空则占位）。"""
    cleaned = "".join(ch for ch in component if ch.isalnum() or ch in "-_.")
    return cleaned or "_"


def user_file_prefix(user_id: str) -> str:
    """用户文件键前缀：``users/<uid>/files/``。"""
    return f"users/{_safe_component(user_id)}/files/"


class UserFileStore:
    """MinIO 实现：客户端与桶惰性建立；失败进冷却期（软依赖不抛）。"""

    def __init__(self, minio_config, local_root: str):
        """
        Args:
            minio_config: MinioConfig，连接与桶配置。
            local_root: 本地回退根目录（MinIO 不可达时同键落盘）。
        """
        self._minio_config = minio_config
        self._local_root = Path(local_root)
        self._client = None
        self._bucket_ready = False
        self._failed_at = 0.0
        self._lock = threading.Lock()

    def _ensure_client(self):
        """惰性构造 MinIO 客户端并自举桶；失败返回 None（调用方走本地回退）。"""
        with self._lock:
            if self._client is not None and self._bucket_ready:
                return self._client
            if self._failed_at and time.monotonic() - self._failed_at < _FAILURE_COOLDOWN:
                return None
            try:
                from minio import Minio
                cfg = self._minio_config
                client = Minio(cfg.endpoint, access_key=cfg.access_key,
                               secret_key=cfg.secret_key, secure=cfg.secure)
                if not client.bucket_exists(cfg.bucket):
                    client.make_bucket(cfg.bucket)
                self._client = client
                self._bucket_ready = True
                self._failed_at = 0.0
                return client
            except Exception as exc:
                self._failed_at = time.monotonic()
                logger.warning("用户文件对象存储不可用，回退本地: %r", exc)
                return None

    def _local_path(self, key: str) -> Path:
        """本地回退根 + 对象键拼成本地路径。"""
        return self._local_root / key

    def put(self, user_id: str, rel_path: str, data: bytes,
            content_type: str = "application/octet-stream") -> str:
        """写入一个用户数据文件，返回对象键（本地回退时同键落盘）。

        Args:
            user_id: 归属用户（键前缀）。
            rel_path: 用户内相对路径（如 ``documents/笔记.md``）。
            data: 文件字节。
            content_type: MIME 类型。

        Returns:
            str: 完整对象键（OSS 与本地回退同键，调用方可存元数据行）。
        """
        key = f"{user_file_prefix(user_id)}{rel_path.lstrip('/')}"
        client = self._ensure_client()
        if client is not None:
            import io
            try:
                client.put_object(self._minio_config.bucket, key,
                                  io.BytesIO(data), length=len(data),
                                  content_type=content_type)
                return key
            except Exception as exc:
                logger.warning("用户文件写入 OSS 失败（%s），回退本地: %r", key, exc)
        target = self._local_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    def get(self, key: str) -> bytes | None:
        """按键取回文件字节（先 OSS 后本地；都没有为 None）。"""
        client = self._ensure_client()
        if client is not None:
            response = None
            try:
                response = client.get_object(self._minio_config.bucket, key)
                return response.read()
            except Exception as exc:
                logger.debug("用户文件 OSS 取回失败（%s）：%s", key, exc)
            finally:
                if response is not None:
                    try:
                        response.close()
                        response.release_conn()
                    except Exception:
                        pass
        local = self._local_path(key)
        if local.exists():
            return local.read_bytes()
        return None

    def delete(self, key: str) -> None:
        """按键删除（OSS 与本地都删；不存在也算成功）。"""
        client = self._ensure_client()
        if client is not None:
            try:
                client.remove_object(self._minio_config.bucket, key)
            except Exception as exc:
                logger.warning("用户文件 OSS 删除失败（%s）：%s", key, exc)
        local = self._local_path(key)
        if local.exists():
            local.unlink()


class NullUserFileStore:
    """空实现：配置明确关闭对象存储时用（put 返回空键、get 恒 None）。"""

    def put(self, user_id, rel_path, data, content_type="application/octet-stream") -> str:
        return ""

    def get(self, key):
        return None

    def delete(self, key):
        return None


def make_user_file_store(config, local_root: str):
    """按配置造用户文件存取器（MinIO 段缺失时给空实现）。

    Args:
        config: BioPilotConfig，取 rag.storage.minio 连接段。
        local_root: 本地回退根目录。

    Returns:
        UserFileStore | NullUserFileStore。
    """
    if not getattr(config.rag.storage, "minio", None):
        return NullUserFileStore()
    return UserFileStore(config.rag.storage.minio, local_root)
