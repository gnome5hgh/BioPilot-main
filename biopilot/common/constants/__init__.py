"""跨层共享的纯取值与枚举；消费方一律从本模块取。"""
from biopilot.common.constants.constants import RETRY_BACKOFF_BASE
from biopilot.common.constants.enums import MessageRole

__all__ = ["RETRY_BACKOFF_BASE", "MessageRole"]
