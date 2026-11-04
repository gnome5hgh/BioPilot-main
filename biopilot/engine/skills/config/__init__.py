"""skills 域组件的自有参数。

与顶层 `biopilot/config/` 分工：那里是「与全局配置树同构、可经设置页或 env 调整」的
全局可调参数；这里是**组件自己的行为参数**，由注册表在加载时构造，不进全局配置。
"""
from biopilot.engine.skills.config.skill_config import SkillConfig

__all__ = ["SkillConfig"]
