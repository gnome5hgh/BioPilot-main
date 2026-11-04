# biopilot/engine/skills/services/user_skills.py
"""用户技能的本地物化缓存。

平台侧（Java）把每个用户安装的技能包存在 OSS（``users/<uid>/skills/<name>/<sha>.zip``），
``bio_skill`` 表是管理真相。引擎只做只读消费：会话装配时把该用户的启用技能物化到
``<user_cache>/<uid>/skills/``，供注册表扫描。

本地目录**只是缓存**：``content_sha`` 对不上就删了重拉；平台不可达时保留旧缓存继续用，
没有缓存则该用户暂时没有额外技能——不阻塞对话。缓存不是真相源，任何时刻都可重建。
"""

import json
import logging
import os
import shutil
import uuid
import zipfile
from pathlib import Path

from biopilot.engine.skills.services.layout import user_skills_cache_dir

logger = logging.getLogger(__name__)

#: 缓存清单文件名（name → content_sha）；点开头，注册表扫描时跳过
_MANIFEST = ".manifest.json"

#: 解包闸门（与 Java 侧安装闸门同口径）
_MAX_ENTRIES = 2000
_MAX_BYTES = 50 * 1024 * 1024


def sync_user_skills(db, platform_client, cache_root: str, user_id: str) -> Path | None:
    """把该用户启用的技能物化到本地缓存目录。

    Args:
        db: MemoryDB 实例（只读 ``bio_skill``；表缺失/查询失败时降级为空）。
        platform_client: 平台内部客户端（``skill_package`` 取包字节）；可为 None。
        cache_root: 按用户隔离的派生缓存根（``config.user_cache_root``）。
        user_id: 归属用户。

    Returns:
        缓存目录路径（存在且有内容时）；无可用技能时返回 None。
    """
    try:
        rows = db.execute(
            "SELECT name, content_sha, enabled FROM bio_skill WHERE user_id=?",
            (user_id,)).fetchall()
    except Exception:
        # 表尚未迁移 / 平台库不可达：技能层降级为空，不阻塞对话
        logger.warning("读取 bio_skill 失败，用户技能按空处理（%s）", user_id, exc_info=True)
        return None

    desired = {
        str(row["name"]): str(row["content_sha"])
        for row in rows
        if row.get("enabled", 1) and str(row.get("name", "")).strip()
    }

    root = user_skills_cache_dir(cache_root, user_id)
    manifest = _read_manifest(root)

    # 清理：不在启用集合里的缓存目录、内容已变化的目录、残留的临时物化目录
    _cleanup(root, desired, manifest)

    if not desired:
        return root if root.is_dir() else None

    changed = False
    for name, sha in desired.items():
        target = root / name
        if target.is_dir() and manifest.get(name) == sha:
            continue
        if platform_client is None:
            logger.warning("缺少平台客户端，保留技能 '%s' 的现有缓存", name)
            continue
        try:
            data, header_sha = platform_client.skill_package(user_id, name)
            actual = header_sha or sha
            if header_sha and sha and header_sha != sha:
                logger.warning("技能 '%s' 内容 sha 与数据库不一致（%s != %s），以实际包为准",
                               name, header_sha, sha)
            _materialize(root, name, data, actual)
            manifest[name] = actual
            changed = True
        except Exception:
            # 平台不可达或包损坏：保留旧缓存（若有），不影响对话
            logger.warning("物化技能 '%s' 失败，保留现有缓存（%s）", name, user_id,
                           exc_info=True)

    if changed:
        _write_manifest(root, manifest)
    return root if root.is_dir() else None


def _materialize(root: Path, name: str, data: bytes, sha: str) -> None:
    """原子物化单个技能：解压到临时目录 → 替换旧目录。

    Args:
        root: 用户技能缓存根。
        name: 技能名。
        data: zip 字节（平台内部端点返回）。
        sha: 内容 sha（写入清单，作为下次比对的键）。
    """
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".{name}.tmp-{uuid.uuid4().hex[:8]}"
    target = root / name
    try:
        tmp.mkdir(parents=True)
        _safe_unzip(data, tmp)
        if target.exists():
            shutil.rmtree(target)
        os.replace(tmp, target)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _safe_unzip(data: bytes, target: Path) -> None:
    """带闸门的解包：拒绝路径穿越、符号链接与超限内容。

    Args:
        data: zip 字节。
        target: 解压目标目录（必须已存在）。

    Raises:
        ValueError: 包结构非法或超过上限。
    """
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_ENTRIES:
            raise ValueError(f"技能包文件数超过上限 {_MAX_ENTRIES}")
        total = sum(info.file_size for info in infos)
        if total > _MAX_BYTES:
            raise ValueError("技能包解压后超过大小上限 50MB")
        base = target.resolve()
        for info in infos:
            name = info.filename
            if name.endswith("/"):
                continue
            member = (target / name).resolve()
            if not member.is_relative_to(base):
                raise ValueError(f"技能包路径越界: {name}")
            # 外部属性高 16 位是 Unix mode；0o120000 = 符号链接
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"技能包含符号链接，拒绝物化: {name}")
            member.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(member, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _cleanup(root: Path, desired: dict[str, str], manifest: dict[str, str]) -> None:
    """删除不再启用/内容已变化/残留临时的缓存目录（尽力而为）。

    Args:
        root: 用户技能缓存根。
        desired: 需要保留的 name → sha。
        manifest: 上次物化记录。
    """
    if not root.is_dir():
        return
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            shutil.rmtree(child, ignore_errors=True)
            continue
        if child.name not in desired:
            shutil.rmtree(child, ignore_errors=True)
            manifest.pop(child.name, None)


def _read_manifest(root: Path) -> dict[str, str]:
    """读取缓存清单；缺失或损坏时返回空映射。"""
    path = root / _MANIFEST
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        logger.warning("技能缓存清单损坏，按空处理：%s", path, exc_info=True)
        return {}


def _write_manifest(root: Path, manifest: dict[str, str]) -> None:
    """原子写缓存清单（临时文件 + os.replace）。"""
    root.mkdir(parents=True, exist_ok=True)
    path = root / _MANIFEST
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)
