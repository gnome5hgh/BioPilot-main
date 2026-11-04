"""路径片段归一化：把用户/会话/文件名变成可安全拼进本地路径的片段。"""
from __future__ import annotations


def safe_component(value: str) -> str:
    """把用户/会话/文件名归一化成可安全拼进本地路径的片段。

    只处理路径分隔符与 ``..``，保留中文等正常文件名字符；空值回退 ``unknown``。

    Args:
        value: 原始片段。

    Returns:
        不含路径分隔符与上跳片段的字符串。
    """
    text = str(value or "").replace("\\", "_").replace("/", "_")
    text = text.replace("\x00", "").strip()
    while ".." in text:
        text = text.replace("..", "_")
    return text or "unknown"
