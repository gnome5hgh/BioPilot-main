"""配置导出：把当前有效配置转成 YAML/JSON（密钥与连接串口令已掩码）。

导出是配置层的职责，供 ``biopilot config export`` 使用；不要从 HTTP 适配层
反向依赖它。引导层字段也会导出，方便换部署时核对。
"""
from __future__ import annotations

import json
from typing import Any

import yaml

from biopilot.config import BioPilotConfig
from biopilot.config.services.schema import (
    effective_map,
    is_secret,
    jsonable,
    mask_dsn,
    mask_model_entries,
)


def _exportable(path: str, value: Any) -> Any:
    """返回适合导出的值：密钥置空，模型清单与 DSN 掩码。"""
    if path == "runtime.models":
        return mask_model_entries(value)
    if is_secret(path):
        return None
    if path == "runtime.memory_dsn":
        return mask_dsn(value)
    return jsonable(value)


def export_yaml(config: BioPilotConfig | None = None) -> str:
    """把当前有效配置导出成 YAML（不含密钥明文）。

    Args:
        config: 可选配置；None 时按当前加载链取一份。

    Returns:
        YAML 文本。
    """
    config = config or BioPilotConfig.from_env()
    tree: dict[str, Any] = {}
    for path, value in effective_map(config).items():
        exported = _exportable(path, value)
        if exported is None and is_secret(path):
            continue
        node = tree
        segments = path.split(".")
        for seg in segments[:-1]:
            node = node.setdefault(seg, {})
        node[segments[-1]] = exported
    return yaml.safe_dump(tree, allow_unicode=True, sort_keys=False)


def export_json(config: BioPilotConfig | None = None) -> str:
    """把当前有效配置导出成 JSON（不含密钥明文）。

    Args:
        config: 可选配置；None 时按当前加载链取一份。

    Returns:
        JSON 文本。
    """
    config = config or BioPilotConfig.from_env()
    payload = {
        path: _exportable(path, value)
        for path, value in effective_map(config).items()
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["export_json", "export_yaml"]
