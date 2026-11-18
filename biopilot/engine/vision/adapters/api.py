"""vision 模块的公开契约（adapters/api.py）：对外功能面 + 组装入口。

模块外（FastAPI 侧、其它 engine 模块）一律经本文件或包根别名使用 vision：
图表分析（结构化）、检索用图注描述、PDF 图表定位与渲染。视觉模型客户端的
构造（出向）同住 ``adapters/``（``builders.py``），同属公开面。
"""
from biopilot.engine.vision.adapters.builders import build_vision_llm
from biopilot.engine.vision.adapters.extractor import FigureExtractor
from biopilot.engine.vision.adapters.renderer import render_figure
from biopilot.engine.vision.application.analyzer import FigureAnalyzer
from biopilot.engine.vision.application.describer import FigureDescriber
from biopilot.engine.vision.constants import FigureType
from biopilot.engine.vision.domain.schemas import Figure, FigureAnalysis

__all__ = [
    "FigureAnalyzer", "FigureDescriber", "FigureExtractor", "render_figure",
    "FigureType", "Figure", "FigureAnalysis", "build_vision_llm", "build_vision",
]


def build_vision(config):
    """构造视觉模型客户端（模块对外唯一的组装入口）。

    Args:
        config: BioPilotConfig（取 ``vision`` 段）。

    Returns:
        LLMClient：视觉模型客户端（duck-typing 兼容 ModelClient 端口）。
    """
    return build_vision_llm(config)
