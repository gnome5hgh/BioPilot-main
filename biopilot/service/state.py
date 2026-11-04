"""进程级共享状态与知识库常量。

这些变量在旧 ``webapi/app.py`` 里就是模块级全局量；refactor 只搬位置，
不改变作用域——测试仍按「查找处」替换这里的属性。
"""
from __future__ import annotations

#: 全部活跃会话的整合队列（键=用户+会话；停服时统一 flush）
_queues: dict[tuple[str, str], object] = {}

#: 会话级模型选择（user -> model 名；None 用默认主模型）
user_models: dict[str, str | None] = {}

#: 正在执行的定时任务 id（进程内去重；跨实例由 Java 的 CAS 认领负责）
_sched_running: set = set()

#: 每用户索引 singleflight（加入知识库与手动重建共用）
reindex_running: set[str] = set()

#: 跑到一半又来了新请求：当前轮结束后再补跑一次
reindex_pending: set[str] = set()

#: 最近一次索引结果（内存态，供知识库页展示；重启后清空）
kb_last_run: dict[str, dict] = {}

#: 单次索引最多重扫几遍
_KB_INDEX_PASSES = 3

#: 索引锁被另一个进程占用时的补跑次数（每次间隔 2 秒）
_KB_LOCK_RETRIES = 15

#: 周期对账间隔（秒）
_KB_SWEEP_SECONDS = 300

#: 知识库只读端点等待 RAG 锁的上限（秒）
_KB_LOCK_WAIT_SECONDS = 5.0
