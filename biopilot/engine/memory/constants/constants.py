"""记忆模块的常量——记忆工具词汇与首启播种的核心块文案。

BASE_MEMORY_TOOLS 是 LLM 面长期记忆工具的词表（只读 1 件）。长期记忆的写入统一
由后台整合完成，不向任何 agent 暴露写工具；装配面由只读召回包
`tools/recall/` 决定，这里是「这一套工具叫什么」的单一声明点，供测试与文档对齐。
整合器的编辑面是结构化指令（动作 + 目标类型），不经过工具名，故不在此列。
"""

__all__ = ["BASE_MEMORY_TOOLS", "DEFAULT_PROFILE", "DEFAULT_ASSISTANT"]

BASE_MEMORY_TOOLS = {"memory_read"}

#: 首启播种的核心记忆块默认文案（profile/assistant 缺失时由 ensure_default_blocks 创建）。
#: assistant 是助手工作方式记忆——与 agents/*/AGENT.md 的静态 system_prompt 分离，
#: 由后台整合随对话演进；profile 是用户画像引导占位，提醒从对话中积累用户画像。
DEFAULT_PROFILE = (
    "用户画像（待维护）：由后台整合从对话中逐步积累用户的身份、偏好、背景。"
)
DEFAULT_ASSISTANT = (
    "工作方式记忆（由 consolidation 维护）：记录与用户协作中学到的"
    "助手角色调整与工作方式偏好；当前为空。"
)
