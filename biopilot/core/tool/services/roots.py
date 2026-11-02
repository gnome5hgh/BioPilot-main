"""语义根映射：工具 ``[目录]`` 提示与写围栏共用的同一份根表。

根名（``ScopeRoot``）是工具描述里的词汇，绝对路径由配置派生。``make_tools``
用它生成提示行；安全侧用它判断写目标是否在声明根内。两处必须同源，否则提示
与实际围栏会漂移。
"""
from pathlib import Path

from biopilot.config import BioPilotConfig
from biopilot.core.tool.constants import ScopeRoot

__all__ = ["_root_map", "semantic_roots", "declared_roots"]


def _root_map(config: BioPilotConfig) -> dict[str, str]:
    """语义根名 → 绝对路径（语料库目录为外部绝对路径，memory 随 workspace）。

    Args:
        config: BioPilotConfig，路径来源。

    Returns:
        语义根名 → 绝对路径的映射（note/pdf/research/memory/analysis/scratch）。
    """
    return {
        ScopeRoot.NOTE: config.corpus.note_dir,
        ScopeRoot.PDF: config.corpus.pdf_dir,
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


def declared_roots(config: BioPilotConfig) -> list[str]:
    """已声明的产物根（写围栏的允许集合）：语义根 + 工作区本身。

    工作区也算在内——记忆块、scratch、引用库、审计都在它下面，agent 在自己
    数据根里的写入属「声明内」，不该平白弹一次确认。返回值全部解析为绝对路径、
    保持顺序并去重，供 WorkspacePolicyMiddleware 判定「写目标在不在声明内」。

    Args:
        config: BioPilotConfig，路径来源。

    Returns:
        list[str]，允许写入的根目录绝对路径列表。
    """
    candidates = list(_root_map(config).values())
    candidates.append(config.runtime.workspace)
    seen: set[str] = set()
    roots: list[str] = []
    for candidate in candidates:
        # 空配置不能当根：Path("").resolve() 会得到当前目录，那等于把整个仓库
        # 当成「声明内」——围栏形同虚设。没配的根直接跳过。
        if not candidate:
            continue
        resolved = str(Path(candidate).resolve())
        if resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)
    return roots
