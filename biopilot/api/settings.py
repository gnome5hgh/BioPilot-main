"""设置页的服务端逻辑：读取有效值、校验补丁、写入数据库、历史与回滚。

接口层只负责鉴权与异常映射；配置的合并语义、密钥掩码和补丁校验都在这里。
HTTP 状态码的映射放在 ``api/app.py``，本模块只抛领域异常。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from biopilot.config import BioPilotConfig, db_source_enabled
from biopilot.config.services import store as config_store
from biopilot.config.services.schema import (
    BOOTSTRAP_PATHS,
    ConfigValidationError,
    build_schema,
    default_map,
    effective_map,
    flatten_leaves,
    is_env_set,
    is_secret,
    jsonable,
    mask_dsn,
    mask_model_entries,
    mask_secret,
    validate_patches,
)
from biopilot.config.services.store import UNSET


class ConfigSourceUnavailable(RuntimeError):
    """当前进程没有启用数据库配置源（例如脚本/测试里的文件模式）。"""


def _require_db() -> None:
    """确认当前进程可以读写数据库配置。

    Raises:
        ConfigSourceUnavailable: 文件模式下调用写入/历史接口。
    """
    if not db_source_enabled():
        raise ConfigSourceUnavailable(
            "当前进程未启用数据库配置源；设置页只在引擎 Web 模式下可用")


def _file_paths() -> set[str]:
    """当前工作目录下 config.yaml 里实际写了的叶子路径。"""
    path = Path.cwd() / "config.yaml"
    if not path.exists():
        return set()
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    return {leaf for leaf, _ in flatten_leaves(data, default_map())}


def _load_snapshot(config: BioPilotConfig) -> tuple[dict, dict, int, str]:
    """读取数据库覆盖；读不到时返回空覆盖与一条面向用户的提示。"""
    if not db_source_enabled():
        return {}, {}, 0, "当前进程未启用数据库配置源，展示的是文件/环境变量的有效值"
    try:
        content, secrets, version = config_store.load_cached(
            config.runtime.memory_dsn, config.runtime.workspace)
        return content, secrets, version, ""
    except Exception as exc:
        return {}, {}, 0, f"配置库读取失败：{exc}"


def snapshot() -> dict[str, Any]:
    """返回设置页需要的全部数据：有效值、来源、版本与字段描述。

    Returns:
        dict: ``version`` / ``values`` / ``sources`` / ``schema`` / ``warning``。
    """
    config = BioPilotConfig.from_env()
    content, secrets, version, warning = _load_snapshot(config)
    db_paths = {path for path, _ in flatten_leaves(content, default_map())} | set(secrets)
    raw_file_paths = _file_paths()
    # 数据库模式下配置文件只剩引导层；文件模式下它仍是运行时配置来源。
    file_paths = (raw_file_paths if not db_source_enabled()
                  else {path for path in raw_file_paths if path in BOOTSTRAP_PATHS})

    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for path, value in effective_map(config).items():
        if path == "runtime.models":
            values[path] = mask_model_entries(value)
        elif is_secret(path):
            values[path] = mask_secret(value)
        elif path == "runtime.memory_dsn":
            values[path] = mask_dsn(value)
        else:
            values[path] = jsonable(value)
        if is_env_set(path):
            sources[path] = "env"
        elif path in db_paths:
            sources[path] = "db"
        elif path in file_paths:
            sources[path] = "file"
        else:
            sources[path] = "default"

    return {
        "version": version,
        "values": values,
        "sources": sources,
        "schema": build_schema(),
        "warning": warning,
    }


def _merge_model_secrets(incoming: list[dict], current: list[dict]) -> list[dict]:
    """把多模型清单里被掩码的 api_key 从旧值补回。

    前端读到的是 ``api_key_set`` / ``api_key_last4``，不会拿到明文；保存时按
    name（缺省 model）匹配旧条目，未显式改密钥就把旧值带回。

    Args:
        incoming: 前端提交的条目。
        current: 当前生效的条目（含明文密钥）。

    Returns:
        补回密钥后的条目列表。
    """
    by_name: dict[str, str] = {}
    by_model: dict[str, str] = {}
    for entry in current or []:
        if not entry.get("api_key"):
            continue
        name = str(entry.get("name") or "")
        model = str(entry.get("model") or "")
        if name:
            by_name[name] = str(entry["api_key"])
        if model:
            by_model[model] = str(entry["api_key"])
    merged: list[dict] = []
    for entry in incoming:
        item = dict(entry)
        item.pop("api_key_set", None)
        item.pop("api_key_last4", None)
        name = str(item.get("name") or "")
        model = str(item.get("model") or "")
        if not item.get("api_key"):
            inherited = by_name.get(name) or by_model.get(model)
            if inherited:
                item["api_key"] = inherited
        merged.append(item)
    return merged


def patch(body: dict, updated_by: str) -> dict[str, Any]:
    """校验并写入一批配置补丁。

    Args:
        body: 请求体 ``{version, reason, patches:[{path,value}|{path,unset}]}``。
        updated_by: 管理员 user_id。

    Returns:
        dict: ``{status, version, applied}``。

    Raises:
        ConfigValidationError: 路径/取值非法或缺少版本号。
        ConfigVersionConflict: 版本号落后。
        ConfigSecretKeyMissing: 写入密钥但没有主密钥。
    """
    version = body.get("version")
    reason = str(body.get("reason") or "").strip()[:255]
    _require_db()
    if not isinstance(version, int) or isinstance(version, bool):
        raise ConfigValidationError("version", "缺少版本号（用于乐观锁）")
    items = body.get("patches")
    if not isinstance(items, list):
        raise ConfigValidationError("patches", "需要补丁数组")

    patches: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict) or not item.get("path"):
            raise ConfigValidationError("patches", "每项都需要 path")
        path = str(item["path"])
        patches[path] = UNSET if item.get("unset") else item.get("value")

    if not patches:
        return {"status": "ok", "version": version, "applied": []}

    config = BioPilotConfig.from_env()
    defaults = default_map()
    # 多模型清单的密钥掩码在通用校验之前还原（校验器只认完整结构）。
    if "runtime.models" in patches and patches["runtime.models"] is not UNSET:
        if not isinstance(patches["runtime.models"], list):
            raise ConfigValidationError("runtime.models", "需要 JSON 数组")
        patches["runtime.models"] = _merge_model_secrets(
            patches["runtime.models"], config.runtime.models)

    # UNSET 不是可校验的值：先摘出来，校验完再放回。
    unset_paths = {path for path, value in patches.items() if value is UNSET}
    pending = {path: value for path, value in patches.items()
               if path not in unset_paths}
    # 空字符串对密钥表示「删除该覆盖项」，对普通字段是合法取值。
    pending = {
        path: (UNSET if is_secret(path) and value == "" else value)
        for path, value in pending.items()
    }
    unset_paths |= {path for path, value in pending.items() if value is UNSET}
    validated = validate_patches(
        {path: value for path, value in pending.items() if value is not UNSET},
        defaults)
    for path in unset_paths:
        validated[path] = UNSET

    new_version = config_store.get_store(
        config.runtime.memory_dsn, config.runtime.workspace
    ).save(validated, expected_version=version, updated_by=updated_by,
           reason=reason or "设置页保存")
    return {
        "status": "ok",
        "version": new_version,
        "applied": list(patches.keys()),
    }


def history(limit: int = 20) -> dict[str, Any]:
    """返回最近的保存历史。"""
    _require_db()
    config = BioPilotConfig.from_env()
    rows = config_store.get_store(
        config.runtime.memory_dsn, config.runtime.workspace).history(limit)
    return {"data": rows}


def rollback(version: int, updated_by: str) -> dict[str, Any]:
    """回滚到指定历史版本。"""
    _require_db()
    config = BioPilotConfig.from_env()
    new_version = config_store.get_store(
        config.runtime.memory_dsn, config.runtime.workspace
    ).rollback(version, updated_by=updated_by)
    return {"status": "ok", "version": new_version}
