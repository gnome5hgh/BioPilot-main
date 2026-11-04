"""记忆层的存储子包：MySQL 连接与建表。

`database.py` 维护整库共用的连接池（事务内连接钉住当前线程，写事务靠行锁
串行化），记忆工具的按域模块（block / message）在其上做行级读写。本包只做
再导出，消费方从 `biopilot.engine.memory.storage` 取。
"""
from biopilot.engine.memory.storage.database import MemoryDB

__all__ = ["MemoryDB"]
