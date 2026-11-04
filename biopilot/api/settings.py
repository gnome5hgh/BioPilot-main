"""兼容旧导入路径：设置服务实现已迁到 ``service/impl/settings_service_impl.py``。"""
from __future__ import annotations

from typing import Any

from biopilot.service.errors import ConfigSourceUnavailable
from biopilot.service.impl.settings_service_impl import SettingsServiceImpl

_service = SettingsServiceImpl()


def snapshot() -> dict[str, Any]:
    """返回设置页需要的全部数据。"""
    return _service.snapshot()


def patch(body: dict, updated_by: str) -> dict[str, Any]:
    """校验并写入一批配置补丁。"""
    return _service.patch(body, updated_by)


def history(limit: int = 20) -> dict[str, Any]:
    """返回最近的保存历史。"""
    return _service.history(limit)


def rollback(version: int, updated_by: str) -> dict[str, Any]:
    """回滚到指定历史版本。"""
    return _service.rollback(version, updated_by)


__all__ = [
    "ConfigSourceUnavailable", "snapshot", "patch", "history", "rollback",
]
