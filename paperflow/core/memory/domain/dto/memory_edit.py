"""记忆整合的单条行级编辑指令契约：整合 LLM 调用产出，MemoryConsolidator 校验后应用。"""
from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["MemoryEdit"]


class MemoryEdit(BaseModel):
    """单条记忆编辑指令：目标类型 + 动作 + 新行 / 匹配前缀。

    target 是类型枚举而非文件名——真实的块 label 由代码按「类型 + 当天日期」拼装，
    模型不碰日期。content 与 match 都带长度上限（防 LLM 输出爆炸）；语义约束
    （rewrite 只给核心块、supersede/drop 必须给 match）在 _validate_edit 里校验。

    Attributes:
        target: Literal["profile","assistant","feedback","project","reference"]，目标类型
        action: Literal["add","supersede","drop","rewrite"]，动作（rewrite 仅限核心块）
        content: str，新行内容（add/supersede）或整块新内容（rewrite），上限取块的字符上限
        match: str，行首前缀；supersede/drop 据此命中旧行，上限 200 字符
    """

    target: Literal["profile", "assistant", "feedback", "project", "reference"]
    action: Literal["add", "supersede", "drop", "rewrite"]
    content: str = Field(default="", max_length=2000)
    match: str = Field(default="", max_length=200)
