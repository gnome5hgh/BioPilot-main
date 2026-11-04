# biopilot/engine/intent/__init__.py
"""意图识别（可选预处理层）的统一导出点。

目录按角色分层：`constants/`（枚举 + 类别词汇/元数据/KB 路径）、`schemas/`（产出契约）、
`rules/`（规则层：实体抽取 + 知识库装载校验）、`services/`（判定服务客户端 + 集成缝）。

集成缝是 `IntentService`（Agent 只持一个可选的它，`None` 即「关」）；类别与规则
来自包内知识库 `engine/intent/data/`，由 `rules.taxonomy.load_taxonomy` 装载并做 fail-closed 校验。
"""
from biopilot.engine.intent.constants import INTENT_CLASSES, IntentStep, IntentType
from biopilot.engine.intent.rules.entities import extract_entities
from biopilot.engine.intent.rules.taxonomy import (
    IntentClass, Rule, Taxonomy, TaxonomyError, load_taxonomy,
)
from biopilot.engine.intent.schemas import IntentOutput
from biopilot.engine.intent.services.jev import JevClient, JevDecision, JevUnavailable
from biopilot.engine.intent.services.service import IntentService, Turn

__all__ = [
    "INTENT_CLASSES", "IntentClass",
    "IntentOutput", "IntentService", "IntentStep", "IntentType",
    "JevClient", "JevDecision", "JevUnavailable",
    "Rule", "Taxonomy", "TaxonomyError", "Turn", "extract_entities", "load_taxonomy",
]
