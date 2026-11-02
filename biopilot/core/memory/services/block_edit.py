"""记忆块的编辑语义：整块重写、按行插入、唯一子串替换。

这些是业务规则（read_only/唯一命中/行号语义），不属于 LLM 工具声明。工具只
负责参数与降级文案；语义放在这里，便于 REPL、测试与其他调用方复用。
"""
from __future__ import annotations

from biopilot.core.memory.services.block_manager import BlockManager

__all__ = ["rewrite_block", "insert_line", "replace_unique"]


def rewrite_block(bm: BlockManager, label: str, new_memory: str) -> str:
    """整块重写：写失败（read_only / 超限）返回错误文本，块缺失抛 KeyError。

    经 mutate_block 原子写入（整块替换也是「读-改-写」，统一走同一入口）。

    Args:
        bm: BlockManager，块 CRUD 服务。
        label: 目标块标签。
        new_memory: 新的整块内容。

    Returns:
        成功返回 "Rewrote block <label>"；写入失败返回错误文本；块缺失抛 KeyError。
    """
    try:
        bm.mutate_block(label, lambda v: new_memory)
    except ValueError as e:
        return f"Error: {e}"
    return f"Rewrote block {label}"


def insert_line(bm: BlockManager, label: str, new_string: str,
                insert_line: int = -1) -> str:
    """把 new_string 插入块的指定行号；insert_line=-1 表示追加到末尾。

    块缺失返回显式「no block」——改既有块的意图不该被静默创建掩盖拼错。
    行号超出末尾时按末尾处理。读-算-写收进 mutate_block 的 mutator，整段一次持锁。

    Args:
        bm: BlockManager，块 CRUD 服务。
        label: 目标块标签。
        new_string: 待插入内容。
        insert_line: 插入行号（-1=末尾，0=开头）。

    Returns:
        成功返回含实际插入行号的文本；块缺失/写入失败返回错误文本。
    """
    resolved_line = insert_line

    def _insert(v: str) -> str:
        nonlocal resolved_line
        lines = v.splitlines()
        at = len(lines) if insert_line == -1 else insert_line
        resolved_line = at
        lines.insert(at, new_string)
        return "\n".join(lines)

    try:
        bm.mutate_block(label, _insert)
    except KeyError:
        return f"Error: no block with label {label}"
    except ValueError as e:
        return f"Error: {e}"
    return f"Inserted into block {label} at line {resolved_line}"


def replace_unique(bm: BlockManager, label: str, old_string: str,
                   new_string: str) -> str:
    """在块内替换子串：old_string 必须唯一出现才替换，0 次或 >1 次都报错。

    强制唯一是因为不明确的子串替换会静默改错位置或重复改；显式要求唯一逼
    LLM 补足上下文。块缺失返回显式「no block」——改既有块的意图不该被静默
    创建掩盖拼错（与 append 的自动建块刻意不对称）。

    Args:
        bm: BlockManager，块 CRUD 服务。
        label: 目标块标签。
        old_string: 待替换的旧子串（须唯一出现）。
        new_string: 新子串。

    Returns:
        成功返回替换说明文本；未命中/多次命中/块缺失都转为错误文本。
    """
    def _replace(v: str) -> str | None:
        occurrences = v.count(old_string)
        if occurrences == 0:
            return None
        if occurrences > 1:
            raise ValueError(
                f"old_string occurs {occurrences} times, must be unique")
        return v.replace(old_string, new_string)

    try:
        if bm.mutate_block(label, _replace) is None:
            return f"Error: old_string not found in block {label}"
    except KeyError:
        return f"Error: no block with label {label}"
    except ValueError as e:
        return f"Error: {e}"
    return f"Updated block {label}: replaced '{old_string}' with '{new_string}'"
