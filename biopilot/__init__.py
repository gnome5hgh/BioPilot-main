"""BioPilot 引擎主包。"""
import os

# 必须在任何可能拉起 gRPC 的导入（biopilot.engine.rag → pymilvus）之前设置——gRPC C
# 核心在初始化时读取。不设时 gRPC 打 INFO 级日志：子进程 fork 时，pymilvus 已建连的
# 轮询 fd 残留会让每个子进程打一行 "FD from fork parent still in poll list"
# （ev_poll_posix.cc），纯噪音。setdefault 不覆盖用户显式配置。
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
