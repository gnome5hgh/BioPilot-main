"""应用生命周期：后台回收/对账与停服收尾。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动后台循环，停服时 flush 整合队列并结束终端 shell。"""
    services = app.state.services
    app.state.shell_reaper = asyncio.create_task(services.terminal.reaper())
    app.state.kb_reconciler = asyncio.create_task(services.kb.reconcile_loop())
    try:
        users = set(await asyncio.to_thread(
            services.kb.users_needing_reconcile))
        users |= set(await asyncio.to_thread(services.kb.users_with_kb))
        for user_id in sorted(users):
            services.kb.schedule_user_index(user_id)
    except Exception:
        logger.warning("启动时知识库状态恢复失败", exc_info=True)

    try:
        yield
    finally:
        await services.chat.flush_consolidations()
        reaper = getattr(app.state, "shell_reaper", None)
        if reaper is not None:
            reaper.cancel()
        try:
            await services.terminal.shutdown()
        except Exception:
            logger.warning("停服结束终端 shell 失败", exc_info=True)
