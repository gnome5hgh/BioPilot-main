"""Web 适配层：把 Agent 装配暴露为本地 HTTP/SSE 服务。

信任边界：本服务只监听内网回环，SpringBoot 内网调用携带的
X-User-Id 即真相，这里不做二次鉴权；缺头即拒绝（fail-closed）。
"""
from biopilot.webapi.app import WebConfig, create_app, run_server

__all__ = ["WebConfig", "create_app", "run_server"]
