"""记忆层的存储子包：MySQL 连接与建表。

`database.py` 是整库唯一连接单例（写事务串行化），记忆工具的按域模块
（block / message）在其上做行级读写。本包只做再导出，消费方从
`biopilot.core.memory.storage` 取。
"""
from biopilot.core.memory.storage.database import MemoryDB

__all__ = ["MemoryDB"]
