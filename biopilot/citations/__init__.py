"""引用管理（溯源落地）：references.bib 读写 + 语料标题索引 + 编排。

分层：`constants/`（枚举）· `schemas/`（数据模型）· `storage/`（bib 文件读写
原语）· `parsers/`（pdf2bib 书目提取）· `services/`（编排、语料索引、key 生成规则）。
对外只经本门面进入——按用户域懒加载 CitationManager；重组件（corpus 索引、
书目提取器）在 CitationManager 内部首次使用时才构造。

**引用库按用户隔离**：每个用户域一份 `users/<uid>/citations/references.bib`，
语料标题索引也指向该用户的 RAG 镜像目录。`local` 域保持原有单机路径，兼容 REPL。
"""
from __future__ import annotations

import re
import threading
from dataclasses import replace
from pathlib import Path

from biopilot.citations.schemas import BibEntry, ResolvedCitation
from biopilot.citations.services.keys import gen_key
from biopilot.citations.services.manager import CitationManager
from biopilot.citations.storage import entry_text

_managers: dict[str, CitationManager] = {}
_managers_lock = threading.Lock()


def _domain_config(config, user_domain: str):
    """给非 local 域派生独立的 bib 路径与语料根。

    Args:
        config: BioPilotConfig，全局配置。
        user_domain: 用户域（登录用户 id 或 local）。

    Returns:
        BioPilotConfig: 语料/引用路径已切到该用户域的新配置。
    """
    domain = user_domain or "local"
    if domain == "local":
        return config
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", domain)
    workspace = Path(config.runtime.workspace)
    corpus = replace(
        config.corpus,
        pdf_dir=str(workspace / "rag" / "users" / safe / "papers"),
        citations_bib_path=str(
            workspace / "users" / safe / "citations" / "references.bib"),
    )
    return replace(config, corpus=corpus)


def get_citation_manager(config=None, user_domain: str = "local") -> CitationManager:
    """按用户域懒加载 CitationManager（同域共享一个实例）。

    Args:
        config: BioPilotConfig | None，缺省按环境加载。
        user_domain: 用户域；local 用单机路径，其余按 users/<uid>/ 隔离。

    Returns:
        CitationManager: 该用户域的引用库门面。
    """
    key = user_domain or "local"
    manager = _managers.get(key)
    if manager is not None:
        return manager
    if config is None:
        from biopilot.config import BioPilotConfig
        config = BioPilotConfig.from_env()
    with _managers_lock:
        if key not in _managers:
            _managers[key] = CitationManager(_domain_config(config, key))
        return _managers[key]


__all__ = ["CitationManager", "ResolvedCitation", "BibEntry", "gen_key", "entry_text",
           "get_citation_manager"]
