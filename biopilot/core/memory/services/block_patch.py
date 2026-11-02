"""记忆块的简化 unified diff 语义（单块模式）。

工具只负责收集 label/patch 与降级文案；diff 解析与应用是业务逻辑，放在本模块。
"""
from __future__ import annotations

import re

from biopilot.core.memory.services.block_manager import BlockManager

__all__ = ["apply_patch"]


def _apply_diff(value: str, patch: str) -> str:
    """就地应用 unified diff：返回改动后的整块文本，语义不符时抛 ValueError。

    删行用前向扫描宽容匹配（LLM 生成的 patch 与实际内容常有漂移），' ' 上下文
    行仍精确位置匹配——宽容删行吸收漂移、精确上下文守住边界。

    Args:
        value: 块当前文本。
        patch: 简化 unified diff。

    Returns:
        应用 patch 后的整块文本。

    Raises:
        ValueError: 上下文行不匹配或删行找不到。
    """
    lines = value.splitlines()
    result: list[str] = []
    i = 0
    for pline in patch.splitlines():
        if pline.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", pline)
            if m:
                target = max(0, int(m.group(1)) - 1)
                while i < target and i < len(lines):
                    result.append(lines[i])
                    i += 1
            continue
        if pline.startswith(" "):
            c = pline[1:]
            if i >= len(lines) or lines[i] != c:
                raise ValueError(f"context line {c!r} not found at position {i + 1}")
            result.append(lines[i])
            i += 1
        elif pline.startswith("-"):
            removed = pline[1:]
            j = i
            while j < len(lines) and lines[j] != removed:
                j += 1
            if j >= len(lines):
                raise ValueError(f"line {removed!r} not found")
            while i < j:
                result.append(lines[i])
                i += 1
            i += 1
        elif pline.startswith("+"):
            result.append(pline[1:])
        elif pline.startswith("\\"):
            continue
    result.extend(lines[i:])
    return "\n".join(result)


def apply_patch(bm: BlockManager, label: str, patch: str) -> str:
    """对指定块应用 patch；块缺失返回显式「no block」，多块 patch 直接拒绝。

    读块 + 应用 patch 收进 mutate_block 的 mutator：patch 应用在持锁内基于最新
    值进行，避免并发下用旧值算出的结果覆盖别人刚写的改动。

    Args:
        bm: BlockManager，块 CRUD 服务。
        label: 目标块标签。
        patch: 简化 unified diff。

    Returns:
        成功返回应用成功文本；多块 patch 直接拒绝，块缺失/语义不符返回错误文本。
    """
    if "*** Add Block:" in patch or "*** Update Block:" in patch:
        return "Error: multi-block patch not supported"

    def _patched(v: str) -> str:
        return _apply_diff(v, patch)

    try:
        bm.mutate_block(label, _patched)
    except KeyError:
        return f"Error: no block with label {label}"
    except ValueError as e:
        return f"Error: {e}"
    return f"Applied patch to block {label}"
