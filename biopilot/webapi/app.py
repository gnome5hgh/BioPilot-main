"""FastAPI 应用工厂：对话 SSE 流 + 健康检查（工单 10）。

SSE 桥接约定：
    - 事件帧：``data: {"type": "token"|"tool"|"round"|"done"|"error", ...}``
    - 流结束帧 type=done 恒发出（含异常路径）——客户端据此判断可复用连接。
    - 客户端断开（Request.is_disconnected）→ 取消 run（复用 Agent 的取消级联，
      与 REPL Ctrl-C 同路径），不留悬挂任务占会话运行锁。

装配策略（工单 11 前的过渡形态）：进程内字典按 (user_id, conversation_id) 缓存
Agent 实例，工厂函数 ``agent_factory`` 可注入替换（测试用 fake Agent 直打 S1 缝）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


@dataclass
class WebConfig:
    """Web 适配层配置（内网端口 / DSN）。

    Attributes:
        host: 监听地址——只允许回环/内网（信任边界的物理前提）。
        port: 监听端口。
        memory_dsn: 记忆库连接串（传给会话装配）。
    """

    host: str = "127.0.0.1"
    port: int = 8300
    memory_dsn: str | None = None


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
    if agent_factory is None:
        agent_factory = _default_agent_factory

    app = FastAPI(title="BioPilot Agent Adapter", docs_url=None, redoc_url=None)
    agents: dict[tuple[str, str], object] = {}

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/chat/stream")
    async def chat_stream(
        request: Request,
        body: dict,
        x_user_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        """对话流：SSE 帧序列（token/tool/round/done）。

        Args:
            request: 原始请求（断开检测用）。
            body: {"task": str, "conversation_id": str}
            x_user_id: 归属用户（SpringBoot 内网调用携带；缺失即 403 拒绝）。

        Returns:
            text/event-stream 流式响应。
        """
        if not x_user_id:
            # fail-closed：无归属用户的请求拒绝（信任边界要求显式携带）
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        task = (body or {}).get("task", "").strip()
        conversation_id = (body or {}).get("conversation_id", "").strip()
        if not task or not conversation_id:
            raise HTTPException(status_code=422, detail="task 与 conversation_id 必填")

        key = (x_user_id, conversation_id)
        if key not in agents:
            built = agent_factory(x_user_id, conversation_id)
            # 工厂可为同步或异步（真实装配是 async，测试替身是同步 lambda）
            agents[key] = await built if asyncio.iscoroutine(built) else built
        agent = agents[key]

        async def event_stream():
            queue: asyncio.Queue = asyncio.Queue()

            def on_event(event) -> None:
                # stream_callback 是同步回调（Agent 线程内直接调）：线程安全投递
                queue.put_nowait({
                    "type": getattr(event, "kind", "token"),
                    "text": getattr(event, "text", "") or "",
                    "agent_type": getattr(event, "agent_type", ""),
                })

            async def run_task() -> str:
                return await agent.run(
                    task, stream_callback=on_event) if _accepts_stream(
                    agent.run) else await agent.run(task)

            async def watch_disconnect() -> None:
                """客户端断开 → 取消 run（复用取消级联，与 REPL Ctrl-C 同路径）。"""
                while True:
                    if await request.is_disconnected():
                        run_handle.cancel()
                        return
                    await asyncio.sleep(0.3)

            async def drain():
                """把队列里的事件转 SSE 帧；run 结束立即补收尾帧。

                竞速等待：queue.get 与 run 完成谁先到处理谁——run 正常完成时立即
                发 done，异常时发 error 帧，不再靠心跳轮询兜底；心跳只服务「run
                长时间无事件」的活性场景。
                """
                run_handle = asyncio.create_task(run_task())
                watcher = asyncio.create_task(watch_disconnect())
                get_op = None
                try:
                    while not run_handle.done():
                        get_op = asyncio.create_task(queue.get())
                        done, _ = await asyncio.wait(
                            {get_op, run_handle},
                            timeout=15, return_when=asyncio.FIRST_COMPLETED)
                        if get_op in done:
                            item = get_op.result()
                            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                            continue
                        get_op.cancel()
                        if run_handle in done:
                            break
                        yield ": keep-alive\n\n"    # 15s 无事件的心跳
                    # run 已结束：排干队列残余事件
                    while not queue.empty():
                        item = queue.get_nowait()
                        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                except asyncio.CancelledError:
                    pass
                finally:
                    watcher.cancel()
                    if get_op is not None and not get_op.done():
                        get_op.cancel()
                    try:
                        answer = await run_handle
                        yield f"data: {json.dumps({'type': 'done', 'text': answer}, ensure_ascii=False)}\n\n"
                    except asyncio.CancelledError:
                        yield f"data: {json.dumps({'type': 'done', 'cancelled': True}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        # 错误一律降级为文本（红线）：error 帧说明原因，done 帧恒发收尾
                        yield f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'errored': True}, ensure_ascii=False)}\n\n"

            async for chunk in drain():
                yield chunk

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


def _accepts_stream(run_callable) -> bool:
    """判断 run 是否接受 stream_callback 参数（fake Agent 可能没有）。"""
    import inspect
    try:
        return "stream_callback" in inspect.signature(run_callable).parameters
    except (TypeError, ValueError):
        return False


async def _default_agent_factory(user_id: str, conversation_id: str):
    """真实装配：委托 assembly 的会话装配（工单 11 展开会话级 bundle 管理）。"""
    from biopilot.cli.services.assembly import assemble_web_session
    return await assemble_web_session(user_id, conversation_id)


def run_server(config: WebConfig | None = None) -> None:
    """阻塞启动 uvicorn（`biopilot web` 子命令的实现体）。"""
    import uvicorn
    cfg = config or WebConfig(
        host=os_env("BIOPILOT_WEB_HOST", "127.0.0.1"),
        port=int(os_env("BIOPILOT_WEB_PORT", "8300")),
        memory_dsn=os_env("BIOPILOT_MEMORY_MYSQL_DSN", None))
    uvicorn.run(create_app(config=cfg), host=cfg.host, port=cfg.port, log_level="info")


def os_env(key: str, default: str | None) -> str | None:
    import os
    return os.environ.get(key, default)
