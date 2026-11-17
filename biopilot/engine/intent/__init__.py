# biopilot/engine/intent/__init__.py
"""意图识别（可选预处理层）的统一导出点。

目录按三层分层：`constants/`（枚举 + 类别词汇/元数据/KB 路径）、`domain/`（schemas/ 产出契约、
rules/ 规则层、data/ 知识库资产）、`application/`（集成缝）、`adapters/`（判定服务客户端）。

集成缝是 `IntentService`（Agent 只持一个可选的它，`None` 即「关」）；类别与规则
来自包内知识库 `engine/intent/domain/data/`，由 `domain.rules.taxonomy.load_taxonomy` 装载并做 fail-closed 校验。
"""
from biopilot.engine.intent.constants import INTENT_CLASSES, IntentStep, IntentType
from biopilot.engine.intent.domain.rules.entities import extract_entities
from biopilot.engine.intent.domain.rules.taxonomy import (
    IntentClass, Rule, Taxonomy, TaxonomyError, load_taxonomy,
)
from biopilot.engine.intent.domain.schemas import IntentOutput
from biopilot.engine.intent.adapters.jev import JevClient, JevDecision, JevUnavailable
from biopilot.engine.intent.application.service import IntentService, Turn

__all__ = [
    "INTENT_CLASSES", "IntentClass",
    "IntentOutput", "IntentService", "IntentStep", "IntentType",
    "JevClient", "JevDecision", "JevUnavailable",
    "Rule", "Taxonomy", "TaxonomyError", "Turn", "extract_entities", "load_taxonomy",
]
