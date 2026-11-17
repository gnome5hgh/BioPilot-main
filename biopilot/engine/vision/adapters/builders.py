"""vision 域适配器的构造工厂（组装根在 vision 域的延伸）。

vision 的应用编排（analyzer/describer）不再自行构造模型客户端：视觉 LLM 客户端
的构造收口到本模块，应用层经惰性 builder 调用消费——「未注入时首次访问才构造、
无 key 时降级」语义原样保留，只是构造动作换了落点。

本模块是应用层 → 适配器 import 的**登记白名单**（架构守护测试的三层边界规则）。
"""
from __future__ import annotations

__all__ = ["build_vision_llm"]


def build_vision_llm(config):
    """按配置构造视觉模型客户端。

    Args:
        config: BioPilotConfig，取 ``vision`` 段（VisionLLMConfig）。

    Returns:
        LLMClient：视觉模型客户端（duck-typing 兼容 ModelClient 端口的 chat 面）。
    """
    from biopilot.engine.llm.adapters.client import LLMClient

    return LLMClient(config.vision)
