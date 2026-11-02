"""记忆块的 create/replace/delete/rename 统一管理语义。

工具层只暴露 action/label/value；这里的 label 查重、read_only 校验与 rename
重建规则属于记忆业务。
"""
from __future__ import annotations

from biopilot.core.memory.services.block_edit import rewrite_block
from biopilot.core.memory.services.block_manager import BlockManager

__all__ = ["manage_block"]


def manage_block(bm: BlockManager, action: str, label: str,
                 value: str | None = None, **kwargs) -> str:
    """按 action 分发到块的增改删查；错误一律返回可读文本。

    Args:
        bm: BlockManager，块 CRUD 服务。
        action: create | replace | delete | rename。
        label: 目标块标签。
        value: 块内容（create/replace 用）；rename 时可作 new_label 兜底。
        **kwargs: rename 的新标签 new_label。

    Returns:
        结果文本；标签冲突/只读/未知动作都返回错误文本。
    """
    # label 在块表无 UNIQUE 约束——create/rename 必须先查重，
    # 否则重复 label 会静默建出「查得到却取不到」的不可达幽灵块。
    if action == "create":
        if bm.get_block_by_label(label) is not None:
            return f"Error: label '{label}' already exists"
        bm.create_block(label, value or "")
        return f"Created block {label}"
    if action == "replace":
        return rewrite_block(bm, label, value or "")
    if action == "delete":
        b = bm.get_block_by_label(label)
        if b is None:
            return f"Error: no block with label {label}"
        if b.read_only:
            return "Error: block is read-only"
        bm.delete_block(b.id)
        return f"Deleted block {label}"
    if action == "rename":
        b = bm.get_block_by_label(label)
        if b is None:
            return f"Error: no block with label {label}"
        new_label = kwargs.get("new_label", value or label)
        if new_label == label:
            return f"Renamed block {label} -> {new_label}"
        if bm.get_block_by_label(new_label) is not None:
            return f"Error: label '{new_label}' already exists"
        bm.create_block(new_label, b.value, limit=b.limit,
                        description=b.description, read_only=b.read_only)
        # rename 是重建（保护元数据迁移到新块），不是删除——走不检查 read_only
        # 的底层 _delete；直接 delete_block 会因 read_only 拒绝留下半完成的孤儿新块。
        bm._delete(b.id)
        return f"Renamed block {label} -> {new_label}"
    return f"Error: unknown action {action}"
