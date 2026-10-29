"""记忆整合的单条行级编辑指令契约：整合 LLM 调用产出，MemoryConsolidator 校验后应用。"""
from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["MemoryEdit"]


class MemoryEdit(BaseModel):
    """单条记忆编辑指令：目标类型 + 动作 + 新行 / 旧行编号。

    target 是类型枚举而非文件名——真实的块 label 由代码按「类型 + 当天日期」拼装，
    模型不碰日期。line 是模型从提示里抄回来的**快照编号**（「已有记忆」每行行首的
    [n]），不是应用时重新数出来的下标：编号与「块 + 整行原文」的对应关系由代码在
    渲染快照时一并建立，应用时按那份映射校验，因此块在期间被改写只会定位失败，
    不会删错行。content 与 line 的语义约束在 _validate_edit 里校验。

    Attributes:
        target: Literal["profile","assistant","feedback","project","reference"]，目标类型
        action: Literal["add","supersede","drop","rewrite"]，动作（rewrite 仅限核心块）
        content: str，新行内容（add/supersede）或整块新内容（rewrite），上限取块的字符上限
        line: int | None，旧行的快照编号（supersede/drop 必填，从 1 开始）
    """

    target: Literal["profile", "assistant", "feedback", "project", "reference"]
    action: Literal["add", "supersede", "drop", "rewrite"]
    content: str = Field(default="", max_length=2000)
    line: int | None = None
