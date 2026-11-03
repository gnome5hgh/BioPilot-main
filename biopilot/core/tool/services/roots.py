"""语义根映射：工具 ``[目录]`` 提示与写围栏共用的同一份根表。

根名（``ScopeRoot``）是工具描述里的词汇，绝对路径由配置派生。``make_tools``
用它生成提示行；安全侧用它判断写目标是否在声明根内。两处必须同源，否则提示
与实际围栏会漂移。
"""
from pathlib import Path

from biopilot.config import BioPilotConfig
from biopilot.core.tool.constants import ScopeRoot

__all__ = ["_root_map", "semantic_roots"]


def _root_map(config: BioPilotConfig) -> dict[str, str]:
    """语义根名 → 绝对路径（产物目录可来自配置，memory 随 workspace）。

    Args:
        config: BioPilotConfig，路径来源。

    Returns:
        语义根名 → 绝对路径的映射（research/memory/analysis/scratch）。
    """
    return {
        ScopeRoot.RESEARCH: config.corpus.research_dir or str(
            Path(config.runtime.workspace) / "research"),
        ScopeRoot.MEMORY: str(Path(config.runtime.workspace) / "memory"),
        ScopeRoot.ANALYSIS: getattr(config.corpus, "analysis_dir", None)
        or str(Path(config.runtime.workspace) / "analysis"),
        ScopeRoot.SCRATCH: str(Path(config.runtime.workspace) / "scratch"),
    }


def semantic_roots(config: BioPilotConfig) -> dict[str, str]:
    """语义根名 → 绝对路径映射（公开供工具复用，如 run_python 定位分析根）。"""
    return _root_map(config)


