"""配置持久化：MySQL 全局配置 + 密钥加密 + 历史快照。

存储分三张表（都归引擎所有，与 ``bio_agent_state`` 等一样由 Python 建表）：

- ``bio_config``：全局配置的稀疏覆盖（``content`` JSON），只存被改过的路径；
  未出现的键回落 ``sections.py`` 的默认值。
- ``bio_config_secret``：密钥字段按路径单独加密存放，与普通配置分开，
  这样 ``content`` 可以安全导出/排障，密钥也能单独轮换。``runtime.models``
  这种「列表里带密钥」的结构整份加密，读取时对每项 ``api_key`` 做掩码。
- ``bio_config_history``：每次保存的整份快照与改动路径，供审计与回滚。

密钥主材料优先取 ``BIOPILOT_CONFIG_KEY``（base64 的 32 字节），缺省时读取
``<workspace>/config.key``；两者都没有则在第一次写入密钥时自动生成后者
（权限 0600），并在日志里提示备份。丢失主密钥无法解密已存密钥，只能重新填写。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from biopilot.config.services.schema import (
    BOOTSTRAP_PATHS,
    ConfigValidationError,
    SCOPE_GLOBAL,
    default_map,
    flatten_leaves,
    is_secret,
    validate_value,
)
from biopilot.core.memory.storage.database import MemoryDB
from biopilot.core.memory.storage.named_lock import NamedLock

logger = logging.getLogger(__name__)

#: 写入补丁时表示「删除该覆盖项、回落默认值/继承值」的哨兵。
UNSET = object()

#: 进程内快照缓存：工具调用会频繁读配置，不能每次打一次库。5 秒足够让
#: 另一个进程（REPL/脚本）的修改被看见，保存时会主动失效本进程缓存。
_CACHE_TTL_SECONDS = 5.0

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any], dict[str, Any], int]] = {}
_stores: dict[tuple[str, str], "ConfigStore"] = {}
_stores_lock = threading.Lock()


class ConfigVersionConflict(RuntimeError):
    """乐观锁冲突：配置已被另一个管理员改过。"""


class ConfigSecretKeyMissing(RuntimeError):
    """存在加密密钥数据，但当前进程拿不到主密钥。"""


class ConfigSecretDecryptError(RuntimeError):
    """主密钥不匹配，无法解密已存密钥。"""


def get_store(dsn: str, workspace: str) -> "ConfigStore":
    """按 DSN + 工作区取共享的配置存储实例。

    Args:
        dsn: 记忆库连接串（配置本身也存这里）。
        workspace: 运行数据根（密钥文件与导入锁放这里）。

    Returns:
        ConfigStore: 进程内共享实例。
    """
    key = (dsn or "", str(workspace or ""))
    with _stores_lock:
        store = _stores.get(key)
        if store is None:
            store = ConfigStore(dsn=dsn, workspace=workspace)
            _stores[key] = store
        return store


def load_cached(dsn: str, workspace: str) -> tuple[dict[str, Any], dict[str, Any], int]:
    """带进程内 TTL 缓存的配置快照读取。

    Args:
        dsn: 记忆库连接串。
        workspace: 运行数据根。

    Returns:
        tuple: ``(非密钥覆盖, 密钥覆盖, 版本号)``；库中无行时返回空覆盖与 0。
    """
    store = get_store(dsn, workspace)
    cache_key = store.cache_key
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1], cached[2], cached[3]
    content, secrets, version = store.load()
    with _cache_lock:
        _cache[cache_key] = (now, content, secrets, version)
    return content, secrets, version


def invalidate_cache(dsn: str, workspace: str) -> None:
    """清除某个存储实例的进程内快照缓存（保存/回滚后调用）。"""
    store = get_store(dsn, workspace)
    with _cache_lock:
        _cache.pop(store.cache_key, None)


class ConfigStore:
    """全局配置的 MySQL 存储。

    Attributes:
        dsn: 记忆库连接串。
        workspace: 运行数据根（绝对路径）。
        db: 共享的 MySQL 连接池。
    """

    def __init__(self, dsn: str, workspace: str):
        """建连并确保配置表存在（MemoryDB 的 init_schema 幂等建表）。

        Args:
            dsn: 记忆库连接串；空串时 MemoryDB 会读环境变量或报错。
            workspace: 运行数据根；密钥文件与导入锁放这里。
        """
        self.dsn = dsn or ""
        self.workspace = Path(workspace or ".").expanduser().resolve()
        self.db = MemoryDB(self.dsn or None)
        self._key_material: bytes | None = None
        self._key_lock = threading.Lock()

    @property
    def cache_key(self) -> str:
        """进程缓存键：DSN + 工作区（密钥文件在同一工作区才共享解密密文）。"""
        return f"{self.dsn}|{self.workspace}"

    # ------------------------------------------------------------------ 密钥
    def _key(self, create: bool) -> bytes:
        """取主密钥；``create=True`` 时允许自动生成密钥文件。

        Args:
            create: 是否允许在没有任何密钥材料时生成 ``<workspace>/config.key``。

        Returns:
            32 字节 AES-GCM 主密钥。

        Raises:
            ConfigSecretKeyMissing: 需要密钥但既没有环境变量也没有密钥文件，
                且 ``create=False``。
        """
        with self._key_lock:
            if self._key_material is not None:
                return self._key_material
            raw = os.environ.get("BIOPILOT_CONFIG_KEY", "").strip()
            if raw:
                self._key_material = _decode_key(raw, "BIOPILOT_CONFIG_KEY")
                return self._key_material

            key_file = self.workspace / "config.key"
            if key_file.exists():
                self._key_material = _decode_key(
                    key_file.read_text().strip(), str(key_file))
                return self._key_material

            if not create:
                raise ConfigSecretKeyMissing(
                    "存在加密密钥但找不到主密钥：请设置 BIOPILOT_CONFIG_KEY，"
                    f"或恢复 {key_file}")
            key = os.urandom(32)
            self.workspace.mkdir(parents=True, exist_ok=True)
            key_file.write_text(base64.urlsafe_b64encode(key).decode())
            os.chmod(key_file, 0o600)
            logger.warning(
                "已生成配置加密密钥 %s；请备份。丢失后已存密钥无法解密，只能重新填写。",
                key_file)
            self._key_material = key
            return key

    def _encrypt(self, value: Any) -> bytes:
        """把任意 JSON 值加密成 ``v1 + nonce + 密文``。"""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        plain = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return b"v1" + nonce + AESGCM(self._key(create=True)).encrypt(
            nonce, plain, b"biopilot-config")

    def _decrypt(self, blob: bytes) -> Any:
        """解密 ``_encrypt`` 的产物；主密钥不匹配时抛可读异常。"""
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if not blob or blob[:2] != b"v1":
            raise ConfigSecretDecryptError("密钥数据格式不认识（缺少版本标记）")
        nonce, ciphertext = blob[2:14], blob[14:]
        try:
            plain = AESGCM(self._key(create=False)).decrypt(
                nonce, ciphertext, b"biopilot-config")
        except InvalidTag as exc:
            raise ConfigSecretDecryptError(
                "主密钥与已存密钥不匹配；请恢复正确的 BIOPILOT_CONFIG_KEY 或 config.key") from exc
        return json.loads(plain.decode("utf-8"))

    # ------------------------------------------------------------------ 读取
    def load(self) -> tuple[dict[str, Any], dict[str, Any], int]:
        """读取当前配置快照。

        Returns:
            tuple: ``(content, secrets, version)``；无行时 ``({}, {}, 0)``。
        """
        cur = self.db.execute(
            "SELECT content, version FROM bio_config WHERE scope=?", (SCOPE_GLOBAL,))
        row = cur.fetchone()
        if not row:
            return {}, {}, 0
        content = _decode_json(row["content"])
        secrets = self._load_secrets(strict=False)
        return content if isinstance(content, dict) else {}, secrets, int(row["version"])

    def _load_secrets(self, strict: bool = True) -> dict[str, Any]:
        """读取并解密密钥覆盖；无密钥行时返回空映射。

        Args:
            strict: 主密钥缺失/不匹配时是否抛错。读取路径传 False（密钥不可用
                不应连累非密钥配置），写入路径传 True（不能在读不到旧密钥时
                覆盖掉它们）。

        Returns:
            路径 → 明文密钥。
        """
        cur = self.db.execute(
            "SELECT path, ciphertext FROM bio_config_secret WHERE scope=?",
            (SCOPE_GLOBAL,))
        rows = cur.fetchall()
        if not rows:
            return {}
        secrets: dict[str, Any] = {}
        for row in rows:
            try:
                secrets[row["path"]] = self._decrypt(bytes(row["ciphertext"]))
            except (ConfigSecretKeyMissing, ConfigSecretDecryptError) as exc:
                if strict:
                    raise
                logger.warning("密钥覆盖无法解密，本次忽略：%s", exc)
                return {}
        return secrets

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        """返回最近的保存历史（不含密钥明文）。

        Args:
            limit: 最多返回多少条（1~200）。

        Returns:
            list[dict]: 每条含 version/changed_paths/updated_by/reason/created_at。
        """
        limit = max(1, min(int(limit), 200))
        cur = self.db.execute(
            "SELECT version, changed_paths, updated_by, reason, created_at"
            " FROM bio_config_history WHERE scope=? ORDER BY version DESC, id DESC"
            " LIMIT ?", (SCOPE_GLOBAL, limit))
        result = []
        for row in cur.fetchall():
            item = dict(row)
            item["changed_paths"] = _decode_json(item.get("changed_paths")) or []
            result.append(item)
        return result

    # ------------------------------------------------------------------ 写入
    def save(self, patches: dict[str, Any], expected_version: int | None,
             updated_by: str, reason: str = "") -> int:
        """原子写入一批补丁，并追加历史快照。

        Args:
            patches: 路径 → 值；值为 ``UNSET`` 表示删除该覆盖项。
            expected_version: 前端读到的版本号；与库中不一致时拒绝（乐观锁）。
                传 None 表示不校验（仅内部迁移使用）。
            updated_by: 修改人（管理员 user_id）。
            reason: 变更说明，写入历史。

        Returns:
            int: 写入后的新版本号。

        Raises:
            ConfigVersionConflict: 版本号不一致（有人先改了）。
        """
        content_patches = {p: v for p, v in patches.items() if not is_secret(p)}
        secret_patches = {p: v for p, v in patches.items() if is_secret(p)}
        changed_paths = list(patches.keys())

        with self.db.transaction():
            cur = self.db.execute(
                "SELECT content, version FROM bio_config WHERE scope=? FOR UPDATE",
                (SCOPE_GLOBAL,))
            row = cur.fetchone()
            current = int(row["version"]) if row else 0
            if expected_version is not None and expected_version != current:
                raise ConfigVersionConflict(
                    f"配置已被其他人修改（当前版本 {current}，提交版本 {expected_version}）")

            content = _decode_json(row["content"]) if row else {}
            if not isinstance(content, dict):
                content = {}
            for path, value in content_patches.items():
                _set_or_unset(content, path, value)
            _prune_empty(content)

            secrets = self._load_secrets() if row else {}
            for path, value in secret_patches.items():
                if value is UNSET or value == "":
                    secrets.pop(path, None)
                    self.db.execute(
                        "DELETE FROM bio_config_secret WHERE scope=? AND path=?",
                        (SCOPE_GLOBAL, path))
                    continue
                secrets[path] = value
                self.db.execute(
                    "INSERT INTO bio_config_secret"
                    " (scope, path, ciphertext, key_version, updated_at)"
                    " VALUES (?, ?, ?, 1, NOW(3))"
                    " ON DUPLICATE KEY UPDATE ciphertext=VALUES(ciphertext),"
                    " key_version=VALUES(key_version), updated_at=NOW(3)",
                    (SCOPE_GLOBAL, path, self._encrypt(value)))

            new_version = current + 1
            content_json = json.dumps(content, ensure_ascii=False)
            if row:
                affected = self.db.execute(
                    "UPDATE bio_config SET content=?, version=?, updated_by=?,"
                    " updated_at=NOW(3) WHERE scope=? AND version=?",
                    (content_json, new_version, updated_by, SCOPE_GLOBAL, current))
                if affected.rowcount == 0:
                    raise ConfigVersionConflict("配置在保存过程中被其他人修改")
            else:
                self.db.execute(
                    "INSERT INTO bio_config"
                    " (scope, content, version, updated_by, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, NOW(3), NOW(3))",
                    (SCOPE_GLOBAL, content_json, new_version, updated_by))

            self._append_history(new_version, content_json, secrets,
                                 changed_paths, updated_by, reason)
        self._invalidate()
        return new_version

    def rollback(self, version: int, updated_by: str) -> int:
        """把配置恢复到某个历史版本，并保留回滚动作本身的历史。

        Args:
            version: 要恢复到的历史版本号。
            updated_by: 操作人。

        Returns:
            int: 回滚后产生的新版本号。

        Raises:
            ValueError: 历史版本不存在。
        """
        cur = self.db.execute(
            "SELECT content, secrets_ciphertext, version FROM bio_config_history"
            " WHERE scope=? AND version=? ORDER BY id DESC LIMIT 1",
            (SCOPE_GLOBAL, version))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"历史版本 {version} 不存在")
        content = _decode_json(row["content"]) or {}
        secrets: dict[str, Any] = {}
        blob = row.get("secrets_ciphertext")
        if blob:
            secrets = self._decrypt(bytes(blob)) or {}

        with self.db.transaction():
            cur = self.db.execute(
                "SELECT version FROM bio_config WHERE scope=? FOR UPDATE",
                (SCOPE_GLOBAL,))
            current = int(cur.fetchone()["version"]) if cur.rowcount else 0
            new_version = current + 1
            content_json = json.dumps(content, ensure_ascii=False)
            if cur.rowcount:
                self.db.execute(
                    "UPDATE bio_config SET content=?, version=?, updated_by=?,"
                    " updated_at=NOW(3) WHERE scope=?",
                    (content_json, new_version, updated_by, SCOPE_GLOBAL))
            else:
                self.db.execute(
                    "INSERT INTO bio_config"
                    " (scope, content, version, updated_by, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, NOW(3), NOW(3))",
                    (SCOPE_GLOBAL, content_json, new_version, updated_by))
            self.db.execute(
                "DELETE FROM bio_config_secret WHERE scope=?", (SCOPE_GLOBAL,))
            for path, value in secrets.items():
                self.db.execute(
                    "INSERT INTO bio_config_secret"
                    " (scope, path, ciphertext, key_version, updated_at)"
                    " VALUES (?, ?, ?, 1, NOW(3))",
                    (SCOPE_GLOBAL, path, self._encrypt(value)))
            self._append_history(
                new_version, content_json, secrets, [], updated_by,
                f"回滚到版本 {version}")
        self._invalidate()
        return new_version

    def _append_history(self, version: int, content_json: str,
                        secrets: dict[str, Any], changed_paths: list[str],
                        updated_by: str, reason: str) -> None:
        """追加一条历史快照（与主表写入在同一事务内）。"""
        self.db.execute(
            "INSERT INTO bio_config_history"
            " (scope, version, content, secrets_ciphertext, changed_paths,"
            "  updated_by, reason, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, NOW(3))",
            (SCOPE_GLOBAL, version, content_json,
             self._encrypt(secrets) if secrets else None,
             json.dumps(changed_paths, ensure_ascii=False),
             updated_by, reason))

    def _invalidate(self) -> None:
        """清除本进程缓存。"""
        with _cache_lock:
            _cache.pop(self.cache_key, None)

    # ------------------------------------------------------------------ 迁移
    def ensure_seeded(self, legacy_path: Path | str | None) -> int | None:
        """库中没有配置行时，把旧 ``config.yaml`` 一次性导入。

        多个进程同时启动时用 MySQL 命名锁串行化（跨进程互斥只认数据库锁）；
        拿不到锁说明另一个进程正在导入，直接返回（下一次读配置就能看到结果）。

        Args:
            legacy_path: 旧配置文件路径；不存在则跳过。

        Returns:
            int | None: 导入后的版本号；没有导入时返回 None。
        """
        _, _, version = self.load()
        if version:
            return None
        path = Path(legacy_path) if legacy_path else None
        if path is None or not path.exists():
            return None
        lock = NamedLock(self.dsn)
        try:
            acquired = lock.acquire("config:import", timeout=5)
        except Exception as exc:
            logger.warning("配置导入锁不可用，跳过自动导入：%s", exc)
            return None
        if not acquired:
            return None
        try:
            _, _, version = self.load()
            if version:
                return None
            return self.import_legacy(path, updated_by="system:import",
                                      rewrite=True)
        finally:
            lock.release("config:import")

    def import_legacy(self, path: Path | str, updated_by: str = "system:import",
                      rewrite: bool = False, force: bool = False) -> int:
        """把旧 YAML 配置导入数据库。

        引导层字段（连接串、外部地址、本机路径）不写入数据库：它们仍由环境变量
        提供，``rewrite=True`` 时原样留在文件里，运行时配置从文件中移除。

        Args:
            path: 旧配置文件路径。
            updated_by: 导入人。
            rewrite: 导入后把文件改写成「只含引导层」，并保留 ``.bak`` 备份。
            force: 库中已有配置行时是否覆盖（默认不覆盖）。

        Returns:
            int: 导入后的版本号。

        Raises:
            ConfigValidationError: 文件里有非法取值。
        """
        path = Path(path)
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict):
            raise ConfigValidationError("config.yaml", "顶层必须是对象")
        defaults = default_map()
        leaves = dict(flatten_leaves(data, defaults))

        _, _, existing = self.load()
        if existing and not force:
            return existing

        patches: dict[str, Any] = {}
        bootstrap: dict[str, Any] = {}
        ignored: list[str] = []
        for raw_path, value in leaves.items():
            if raw_path in BOOTSTRAP_PATHS:
                bootstrap[raw_path] = value
                continue
            if raw_path not in defaults:
                ignored.append(raw_path)
                continue
            if is_secret(raw_path) and value in (None, ""):
                continue
            patches[raw_path] = validate_value(raw_path, value, defaults[raw_path])
        if ignored:
            logger.warning("旧配置里有 %d 个已不存在的键，已忽略：%s",
                           len(ignored), ", ".join(sorted(ignored)))

        version = self.save(
            patches, expected_version=None, updated_by=updated_by,
            reason=f"导入 {path.name}")

        if rewrite:
            _rewrite_bootstrap_only(path, bootstrap)
        return version


# ── 通用辅助 ────────────────────────────────────────────────────────────────

def _decode_key(raw: str, source: str) -> bytes:
    """解析 base64 主密钥；长度必须是 32 字节（AES-256）。

    Args:
        raw: base64 文本。
        source: 来源描述，用于报错。

    Returns:
        32 字节密钥。

    Raises:
        ConfigSecretKeyMissing: 不是合法的 base64 或长度不对。
    """
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception as exc:
        raise ConfigSecretKeyMissing(f"{source} 不是合法的 base64 密钥") from exc
    if len(key) != 32:
        raise ConfigSecretKeyMissing(f"{source} 必须是 32 字节（base64 编码后 44 字符）")
    return key


def _decode_json(value: Any) -> Any:
    """把 PyMySQL 返回的 JSON 列（通常是字符串）还原成 Python 对象。"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _set_or_unset(root: dict[str, Any], path: str, value: Any) -> None:
    """在嵌套字典里按路径写值；``UNSET`` 表示删除该键。"""
    segments = path.split(".")
    node = root
    for seg in segments[:-1]:
        child = node.get(seg)
        if not isinstance(child, dict):
            child = {}
            node[seg] = child
        node = child
    if value is UNSET:
        node.pop(segments[-1], None)
    else:
        node[segments[-1]] = value


def _prune_empty(node: dict[str, Any]) -> None:
    """递归删除空对象，避免删除覆盖项后留下无意义的空壳。

    只清理空字典，不动空列表——空列表（如 ``runtime.models: []``）是合法取值。
    """
    for key in list(node):
        value = node[key]
        if isinstance(value, dict):
            _prune_empty(value)
            if not value:
                node.pop(key, None)


def _rewrite_bootstrap_only(path: Path, bootstrap: dict[str, Any]) -> None:
    """把旧配置文件改写成「只含引导层」，并留一份 0600 备份。

    Args:
        path: 原文件路径。
        bootstrap: 引导层字段的扁平映射。
    """
    backup = path.with_name(path.name + ".bak")
    if not backup.exists():
        backup.write_text(path.read_text())
        os.chmod(backup, 0o600)
        logger.warning("旧配置已备份到 %s（含密钥，确认迁移无误后请删除）", backup)

    tree: dict[str, Any] = {}
    for flat_path, value in bootstrap.items():
        _set_or_unset(tree, flat_path, value)
    header = (
        "# 运行时配置已迁入数据库（设置页维护）。\n"
        "# 本文件只剩部署引导项；迁移到环境变量后可以删除。\n"
    )
    path.write_text(header + yaml.safe_dump(
        tree, allow_unicode=True, sort_keys=False))
    os.chmod(path, 0o600)
