"""通用 MinIO 对象存取原语（不含 BioPilot 用户前缀约定）。

只给 agent 侧工具使用（`save_document` 成稿、`run_python` 产物、聊天附件取回）；
平台文件管理（上传/列表/删除/键约定）归 Java。MinIO 不可达时回退本地同键目录，
保证引擎单机（REPL）仍能工作。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: 连接失败后的冷却时间（秒）：避免按文件重复等超时
_FAILURE_COOLDOWN = 60.0


class MinioObjectStore:
    """MinIO 对象存取：connect 惰性建立，失败进冷却期并回退本地。"""

    def __init__(self, minio_config, local_root: str | Path | None = None):
        """
        Args:
            minio_config: 含 endpoint/access_key/secret_key/bucket/secure 的配置对象。
            local_root: 本地回退根目录（None 时只走 MinIO）。
        """
        self._cfg = minio_config
        self._local_root = Path(local_root) if local_root else None
        self._client = None
        self._bucket_ready = False
        self._failed_at = 0.0
        self._lock = threading.Lock()

    def _ensure_client(self):
        """惰性构造客户端并自举 bucket；失败返回 None（调用方回退本地）。"""
        with self._lock:
            if self._client is not None and self._bucket_ready:
                return self._client
            if self._failed_at and time.monotonic() - self._failed_at < _FAILURE_COOLDOWN:
                return None
            try:
                from minio import Minio
                cfg = self._cfg
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
                logger.warning("对象存储不可用，回退本地: %r", exc)
                return None

    def put(self, key: str, data: bytes,
            content_type: str = "application/octet-stream") -> bool:
        """写入对象；成功返回 True，MinIO 不可用时回退本地并返回 False。"""
        client = self._ensure_client()
        if client is not None:
            import io
            try:
                client.put_object(self._cfg.bucket, key, io.BytesIO(data),
                                  length=len(data), content_type=content_type)
                return True
            except Exception as exc:
                logger.warning("对象写入失败（%s），回退本地: %r", key, exc)
        if self._local_root is not None:
            target = self._local_root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return False

    def get(self, key: str) -> bytes | None:
        """按键取回字节；先 MinIO 后本地。"""
        client = self._ensure_client()
        if client is not None:
            response = None
            try:
                response = client.get_object(self._cfg.bucket, key)
                return response.read()
            except Exception as exc:
                logger.debug("对象取回失败（%s）：%s", key, exc)
            finally:
                if response is not None:
                    try:
                        response.close()
                        response.release_conn()
                    except Exception:
                        pass
        if self._local_root is not None:
            local = self._local_root / key
            if local.exists():
                return local.read_bytes()
        return None

    def delete(self, key: str) -> None:
        """删除对象；不存在也算成功。"""
        client = self._ensure_client()
        if client is not None:
            try:
                client.remove_object(self._cfg.bucket, key)
            except Exception as exc:
                logger.warning("对象删除失败（%s）：%r", key, exc)
        if self._local_root is not None:
            local = self._local_root / key
            if local.exists():
                local.unlink()


def make_object_store(config) -> MinioObjectStore | None:
    """按配置构造对象存储；未配置 minio 段时返回 None（调用方降级）。"""
    minio_cfg = getattr(getattr(config, "rag", None), "storage", None)
    minio_cfg = getattr(minio_cfg, "minio", None) if minio_cfg is not None else None
    if minio_cfg is None:
        return None
    local_root = Path(getattr(config.runtime, "workspace", ".biopilot")) / "user-files"
    return MinioObjectStore(minio_cfg, local_root)
