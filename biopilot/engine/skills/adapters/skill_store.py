"""bio_skill 表的只读 SQL 访问（适配层）。

技能管理真相在平台侧（Java 写 ``bio_skill``），引擎按单写者规则只读：
``enabled``/``content_sha`` 两列供物化缓存对账。本模块只做「SQL 行 → 启用清单」
的翻译；降级语义（表缺失/库不可达按空处理）由应用层承担。
"""
from __future__ import annotations

__all__ = ["read_enabled_skills"]


def read_enabled_skills(db, user_id: str) -> dict[str, str]:
    """读该用户全部启用技能的 name → content_sha 清单。

    Args:
        db: MemoryDB，连接池（只读 bio_skill）。
        user_id: 归属用户（行级隔离键）。

    Returns:
        dict[str, str]：启用技能的 name → content_sha（名字去空白后非空才收录）。
    """
    rows = db.execute(
        "SELECT name, content_sha, enabled FROM bio_skill WHERE user_id=?",
        (user_id,)).fetchall()
    return {
        str(row["name"]): str(row["content_sha"])
        for row in rows
        if row.get("enabled", 1) and str(row.get("name", "")).strip()
    }
