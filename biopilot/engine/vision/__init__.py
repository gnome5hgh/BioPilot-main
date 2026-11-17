"""视觉分析子包：PDF 图表提取 + 视觉模型看图分析。

三层职责：``domain/``（数据模型、共用几何、常量词汇）、``application/``（视觉分析编排
与纯算法：analyzer/describer/detectors/parsers）、``adapters/``（PyMuPDF 外部世界翻译：
extractor/renderer/text_extractor）。包根只做再导出。
"""
from biopilot.engine.vision.domain.schemas import Figure, FigureAnalysis
from biopilot.engine.vision.application.analyzer import FigureAnalyzer
from biopilot.engine.vision.adapters.extractor import FigureExtractor
from biopilot.engine.vision.adapters.renderer import render_figure

__all__ = [
    "FigureExtractor", "FigureAnalyzer", "render_figure", "Figure", "FigureAnalysis",
]
