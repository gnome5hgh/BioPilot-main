"""FastAPI 应用工厂与启动入口。"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from biopilot.api.exception_handlers import register_exception_handlers
from biopilot.api.lifespan import lifespan
from biopilot.api.router import api_router
from biopilot.common.utils.env import os_env
from biopilot.domain.runtime_state import RuntimeState
from biopilot.domain.web_config import WebConfig
from biopilot.service.container import build_services

logger = logging.getLogger(__name__)


def create_app(agent_factory=None, config: WebConfig | None = None) -> FastAPI:
    """创建 FastAPI 应用。

    Args:
        agent_factory: ``async (user_id, conversation_id) -> Agent`` 工厂；缺省走
            真实装配（延迟到首请求，避免 import 期拉起 Milvus/LLM 客户端）。
            测试注入 fake Agent 即可直打 S1 缝。
        config: Web 配置；None 用默认（回环 + 8300）。

    Returns:
        配置完成的 FastAPI 实例。
    """
    config = config or WebConfig()
    runtime = RuntimeState.create(config)
    services = build_services(config, runtime, agent_factory=agent_factory)
    app = FastAPI(title="BioPilot Agent Adapter", docs_url=None,
                  redoc_url=None, lifespan=lifespan)
    app.state.runtime = runtime
    app.state.services = services
    app.include_router(api_router)
    register_exception_handlers(app)
    return app


def run_server(config: WebConfig | None = None) -> None:
    """阻塞启动 uvicorn（`biopilot` / `python -m biopilot` 的实现体）。"""
    import uvicorn
    from biopilot.config import enable_db_source, ensure_legacy_import

    # 运行时可调配置的真相源是数据库；入口处统一打开，避免各请求各自判断。
    enable_db_source()
    # 首次部署：把旧的 config.yaml 一次性导入（之后文件只剩引导层）。
    ensure_legacy_import()
    cfg = config or WebConfig(
        host=os_env("BIOPILOT_WEB_HOST", "127.0.0.1"),
        port=int(os_env("BIOPILOT_WEB_PORT", "8300")),
        memory_dsn=os_env("BIOPILOT_MEMORY_MYSQL_DSN", None))
    uvicorn.run(create_app(config=cfg), host=cfg.host, port=cfg.port,
                log_level="info")
