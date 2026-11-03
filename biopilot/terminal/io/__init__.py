"""REPL 输入适配：契约 + 两种终端实现 + 按终端类型装配的工厂。

`base.py` 定义契约与并发确认锁，`interactive.py`（TTY）与 `fallback.py`（非 TTY）
是它的两个可互换实现。本包只做再导出与装配——消费方（cli / repl / 测试）从
`biopilot.terminal.io` 取，不直接引内部模块路径。
"""
import sys

from .base import InputIO
from .fallback import FallbackIO
from .interactive import PromptToolkitIO


def make_input_io(config) -> InputIO:
    """
    工厂函数，根据终端类型装配合适的输入适配器。

    Args:
        config: 配置对象（保留参数以维持装配签名；TTY 历史只在进程内，不读写磁盘）。

    Returns:
        InputIO: 若标准输入为 TTY，则返回 PromptToolkitIO 实例；否则返回
                 FallbackIO 实例（用于管道/CI/测试）。

    Note:
        输入历史只在进程内保留，不落盘；退出 REPL 后不保留、不写入任何文件。
    """
    if sys.stdin.isatty():
        return PromptToolkitIO()
    return FallbackIO()


__all__ = ["InputIO", "FallbackIO", "PromptToolkitIO", "make_input_io"]
