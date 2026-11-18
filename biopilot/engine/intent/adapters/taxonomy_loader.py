"""意图知识库的装载（adapters）：YAML 资产读取 + fail-closed 校验。

领域层（``domain/rules/taxonomy.py``）只做「映射 → Taxonomy」的纯校验；文件 I/O
与资产定位属于适配层。知识库随包发布（``engine/intent/domain/data/``）。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from biopilot.engine.intent.constants import RULES_PATH, TAXONOMY_PATH
from biopilot.engine.intent.domain.rules.taxonomy import Taxonomy, TaxonomyError, taxonomy_from_raw

__all__ = ["load_taxonomy"]


def _read_yaml(path: Path, what: str) -> dict:
    """读一份知识库 YAML；文件缺失或不是映射都视为配置错误。

    Args:
        path: Path，知识库文件路径。
        what: str，人类可读的名字（报错用）。

    Returns:
        dict：YAML 顶层映射。

    Raises:
        TaxonomyError: 文件不存在、解析失败、或顶层不是映射。
    """
    if not path.exists():
        raise TaxonomyError(f"{what}不存在：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"{what}解析失败：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise TaxonomyError(f"{what}顶层必须是映射，实际是 {type(data).__name__}：{path}")
    return data


def load_taxonomy(taxonomy_path: Path | None = None,
                  rules_path: Path | None = None) -> Taxonomy:
    """装载意图知识库并做完整性校验（fail-closed）。

    Args:
        taxonomy_path: Path | None，类别知识库路径；None 用随仓库发布的默认路径。
        rules_path: Path | None，规则层路径；None 用随仓库发布的默认路径。

    Returns:
        Taxonomy：校验通过的类别表与规则表。

    Raises:
        TaxonomyError: 任一份资产缺失、解析失败或校验不过（报错点名具体类别）。
    """
    raw_classes = _read_yaml(taxonomy_path or TAXONOMY_PATH, "意图类别知识库")
    raw_rules = _read_yaml(rules_path or RULES_PATH, "规则层知识库")
    return taxonomy_from_raw(raw_classes, raw_rules)
