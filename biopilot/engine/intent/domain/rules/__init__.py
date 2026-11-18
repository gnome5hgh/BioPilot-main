"""规则层：确定性实体抽取 + 知识库模型与模式匹配。

规则层是判定链的第一层——命中即定类、不命中即放行，**永不猜测**。它的覆盖面故意窄：
只收「说了这句基本不可能是别的意思」的说法，因为误命中的代价高于多跑一次判定服务。
知识库装载（YAML I/O）在 ``adapters/taxonomy_loader.py``；本层只有纯校验与匹配。
"""
from biopilot.engine.intent.domain.rules.entities import extract_entities
from biopilot.engine.intent.domain.rules.taxonomy import (
    IntentClass, Rule, Taxonomy, TaxonomyError, taxonomy_from_raw,
)

__all__ = ["IntentClass", "Rule", "Taxonomy", "TaxonomyError",
           "extract_entities", "taxonomy_from_raw"]
