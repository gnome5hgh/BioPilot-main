"""intent 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块）一律经本文件或包根别名使用 intent：
意图识别服务、知识库装载、判定客户端（外部 HTTP）。判定服务是出向实现，
同住 ``adapters/``，同属公开面。
"""
from biopilot.engine.intent.adapters.jev import JevClient, JevDecision, JevUnavailable
from biopilot.engine.intent.adapters.taxonomy_loader import load_taxonomy
from biopilot.engine.intent.application.service import IntentService, Turn
from biopilot.engine.intent.constants import INTENT_CLASSES, IntentStep, IntentType
from biopilot.engine.intent.domain.rules.entities import extract_entities
from biopilot.engine.intent.domain.rules.taxonomy import (
    Taxonomy,
    TaxonomyError,
    taxonomy_from_raw,
)
from biopilot.engine.intent.domain.schemas import IntentOutput

__all__ = [
    "IntentService", "IntentOutput", "Turn",
    "Taxonomy", "TaxonomyError", "taxonomy_from_raw", "load_taxonomy",
    "extract_entities", "INTENT_CLASSES", "IntentStep", "IntentType",
    "JevClient", "JevDecision", "JevUnavailable",
    "build_intent",
]


def build_intent(taxonomy: Taxonomy, judge: JevClient,
                 history_messages: int = 6) -> IntentService:
    """装配意图识别服务（模块对外唯一的组装入口）。

    Args:
        taxonomy: 已装载的意图知识库（``load_taxonomy`` 产物）。
        judge: 判定服务客户端（外部 HTTP；不可达时调用方整层不装配）。
        history_messages: 判定时携带的历史轮数。

    Returns:
        IntentService。
    """
    return IntentService(taxonomy=taxonomy, judge=judge,
                         history_messages=history_messages)
