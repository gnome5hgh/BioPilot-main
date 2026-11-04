"""AnalyzeFiguresTool：从平台 PDF 字节提取图表并用视觉模型结构化分析。

输入只接受平台 id（paper/file），不再有本地路径与 ``embed_dir``；需要留存图片时
把每张图上传为分析产物并返回 ``file_id``。
"""
import asyncio
import re

from biopilot.common.platform import PlatformError
from biopilot.config import BioPilotConfig
from biopilot.engine.llm import LLMClient
from biopilot.engine.tool import Tool, ToolResult
from biopilot.engine.vision import FigureAnalyzer, FigureExtractor
from biopilot.tools.file._support import (
    content_type_for, current_run_id, current_user_id, platform_for,
)

#: 单次分析图数上限（防超长论文拖死工具；超限截断并如实标注）
MAX_FIGURES = 12


class AnalyzeFiguresTool(Tool):
    """提取并分析 PDF 图表的工具（视觉模型看图，可选把图登记为产物）。

    Attributes:
        name: str，工具名 "analyze_figures"
        description: str，工具描述
        parameters: dict，JSON Schema（id/kind/figure/save_figures）
        risk_level: str，"low"
        provenance: str，"image"
        side_effects: list[str]，["read_file", "write_file"]
        needs_parent: bool，True（视觉调用归属父 agent 轮次进审计）
    """
    name = "analyze_figures"
    description = ("提取并分析平台 PDF 中的图表：视觉模型看图，返回每张图的分析"
                   "（核心内容/图表类型/新颖之处/适用场景/制作工具推测/配色布局标注）。"
                   "figure 指定图号则只分析该图，否则分析全部（最多 12 张）。"
                   "save_figures=true 时把图登记到文件管理并返回 file_id。")
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "file_id",
                   "description": "论文/文件 id"},
            "kind": {"type": "string", "enum": ["paper", "file", "data"],
                     "description": "paper 或 file/data；默认 paper"},
            "figure": {"type": "integer", "description": "只分析指定图号；缺省分析全部"},
            "save_figures": {"type": "boolean",
                             "description": "把图片登记为分析产物；默认 false"},
        },
        "required": ["id"],
    }
    risk_level = "low"
    provenance = "image"
    side_effects = ["read_file", "write_file"]
    needs_parent = True

    def __init__(self, vision_llm=None):
        """视觉模型可注入（测试）；None 时按配置惰性构造。

        Args:
            vision_llm: 视觉模型客户端（LLMClient(VisionLLMConfig)）；测试传假件。
        """
        self._vision_llm = vision_llm

    def _get_vision_llm(self):
        """取视觉模型客户端；vision api_key 未配置返回 None（调用方降级）。"""
        if self._vision_llm is not None:
            return self._vision_llm
        cfg = getattr(self, "_config", None) or BioPilotConfig.from_env()
        if not cfg.vision.api_key:
            return None
        return LLMClient(cfg.vision)

    def effective_target_key(self, args: dict) -> str | None:
        """确认键作用域：按 PDF id 分组（同一篇的多张图共享一次确认）。"""
        target = args.get("id")
        if not isinstance(target, str) or not target:
            return None
        return f"figures:{current_user_id()}:{target}"

    def execute(self, id: str, kind: str = "paper", figure: int | None = None,
                save_figures: bool = False) -> ToolResult:
        """取回 PDF 字节 → 提取图表 → 视觉分析 → 可选登记图片。

        Args:
            id: 论文/文件 id。
            kind: paper/file/data。
            figure: 指定图号只分析该图；None 分析全部。
            save_figures: 是否把图片登记为分析产物。

        Returns:
            ToolResult：text 为逐图分析 digest；任何故障降级为文本。
        """
        llm = self._get_vision_llm()
        if llm is None:
            return ToolResult(
                text="图表分析不可用：未配置视觉模型 key（BIOPILOT_VISION_API_KEY）。",
                summary={"figures": []})
        user = current_user_id()
        platform = platform_for(self)
        attachment_kind = "paper" if kind == "paper" else "file"
        try:
            data, meta = platform.attachment(user, attachment_kind, id)
        except PlatformError as e:
            platform.close()
            return ToolResult(text=f"图表提取失败：{e}", summary={"figures": []})
        try:
            figures = FigureExtractor().extract(data)
        except Exception as e:
            platform.close()
            return ToolResult(text=f"图表提取失败：{e}", summary={"figures": []})
        if not figures:
            platform.close()
            return ToolResult(text="该 PDF 未检测到图表（无图注/无图区）",
                              summary={"figures": []})
        if figure is not None:
            target = str(figure)
            matched = [f for f in figures
                       if str(f.number) == target or f.name == target]
            if not matched:
                known = "、".join(f.name or str(f.number) for f in figures)
                platform.close()
                return ToolResult(
                    text=f"PDF 中未找到 Fig.{figure}（已检测到图号：{known}）",
                    summary={"figures": []})
            figures = matched
        truncated = len(figures) > MAX_FIGURES
        if truncated:
            figures = figures[:MAX_FIGURES]

        try:
            analyzer = FigureAnalyzer(llm, telemetry_callback=self._telemetry())
            analyses = asyncio.run(_analyze_all(analyzer, figures))
            pdf_stem = str(meta.get("name") or "paper").rsplit(".", 1)[0]
            lines: list[str] = []
            embedded: list[dict] = []
            for fig, analysis in zip(figures, analyses):
                if isinstance(analysis, Exception):
                    lines.append(f"### Fig.{fig.name or fig.number} {fig.caption}")
                    lines.append("- 分析失败：视觉模型调用异常，该图已跳过")
                    lines.append("")
                    continue
                file_id = ""
                if save_figures:
                    file_id = _save_figure(user, platform, fig, pdf_stem, id)
                lines.append(f"### Fig.{fig.name or fig.number} {fig.caption}")
                lines.append(f"- 核心内容：{analysis.insight}")
                lines.append(f"- 图表类型：{analysis.chart_type}")
                lines.append(f"- 新颖之处：{analysis.notable}")
                lines.append(f"- 适用场景：{analysis.applicable_scenarios}")
                lines.append(f"- 制作工具推测：{analysis.tool_guess}")
                lines.append(f"- 配色：{analysis.color_scheme}；布局：{analysis.layout_tips}；"
                             f"字体标注：{analysis.font_annotation}")
                if file_id:
                    lines.append(f"- 图片 file_id：{file_id}")
                lines.append("")
                embedded.append({**analysis.model_dump(), "file_id": file_id})
            if truncated:
                lines.append(f"（仅展示前 {MAX_FIGURES} 张，其余省略）")
            return ToolResult(text="\n".join(lines), summary={"figures": embedded})
        except Exception as e:
            return ToolResult(text=f"图表分析失败：{e}", summary={"figures": []})
        finally:
            platform.close()


async def _analyze_all(analyzer: FigureAnalyzer, figures: list) -> list:
    """并行分析多张图；单图异常不短路整批。"""
    return await asyncio.gather(*[analyzer.analyze(f) for f in figures],
                                return_exceptions=True)


def _save_figure(user: str, platform, fig, pdf_stem: str, source_id: str) -> str:
    """把一张图登记为分析产物，返回 file_id；失败返回空串（不打断分析）。"""
    ext = {"image/png": "png", "image/jpeg": "jpg"}.get(fig.mime, "img")
    label = re.sub(r"[/\\\s]+", "_", fig.name or str(fig.number))
    name = f"{pdf_stem}-fig{label}.{ext}"
    try:
        created = platform.upload_artifact(
            user, current_run_id(), name, fig.image_bytes,
            content_type_for(name))
        return str(created.get("file_id") or "")
    except Exception:
        return ""
