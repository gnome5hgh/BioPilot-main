"""视觉分析域包。

公开面统一在 ``adapters/api.py``（本文件只做它的再导出别名）：图表结构化分析
（``FigureAnalyzer``）、检索用图注描述（``FigureDescriber``）、PDF 图表定位与
渲染（``FigureExtractor`` / ``render_figure``）。分层：domain（几何/图式）→
application（分析/描述/检测/解析）→ adapters（PyMuPDF 管线与视觉客户端构造）。
模块外一律经 ``adapters.api`` 或本别名 import。
"""
from biopilot.engine.vision.adapters.api import *  # noqa: F401,F403
from biopilot.engine.vision.adapters.api import __all__ as _api_all

__all__ = list(_api_all)
