"""对话 SSE 流、确认往返与轮末整合收尾实现。"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from biopilot.domain.runtime_state import RuntimeState
from biopilot.domain.web_config import WebConfig
from biopilot.service import state
from biopilot.service.assembly_service import AssemblyService
from biopilot.service.attachment_service import AttachmentService
from biopilot.service.chat_service import ChatService
from biopilot.service.errors import NotFoundError, RequestValidationError, TooManyRequestsError
from biopilot.service.impl.attachment_service_impl import ATTACHMENT_HEADER
from biopilot.service.session_service import SessionService

logger = logging.getLogger(__name__)

#: 确认框里不展示取值的参数名（凭证类一律脱敏）
_SECRET_PARAM_KEYS = {
    "api_key", "apikey", "token", "password", "secret", "access_key",
    "secret_key",
}


def _confirm_params_view(params) -> dict:
    """把工具入参整理成确认框可展示的扁平字典。

    Args:
        params: 工具入参 dict（策略引擎提供的原始参数）。

    Returns:
        dict: 键为参数名、值为字符串的展示视图；不是 dict 时返回空字典。
    """
    if not isinstance(params, dict):
        return {}
    view = {}
    for key, value in params.items():
        name = str(key)
        if name.lower() in _SECRET_PARAM_KEYS:
            view[name] = "***"
            continue
        text = value if isinstance(value, str) else repr(value)
        view[name] = text if len(text) <= 500 else text[:500] + "…"
    return view


class ChatServiceImpl(ChatService):
    """对话 SSE 流、确认往返与轮末整合收尾。"""

    def __init__(self, config: WebConfig, runtime: RuntimeState,
                 assembly: AssemblyService, attachments: AttachmentService,
                 session: SessionService, agent_factory=None):
        self._config = config
        self._runtime = runtime
        self._assembly = assembly
        self._attachments = attachments
        self._session = session
        self._agent_factory = agent_factory or assembly.default_agent_factory

    async def _handle_confirm(self, user_id: str, conversation_id: str,
                              req) -> bool:
        """把确认请求推给浏览器并等待决定；超时/无活动流按拒绝处理。"""
        queue = self._runtime.active_queues.get((user_id, conversation_id))
        if queue is None:
            logger.warning("确认请求无活动流可投递，按拒绝处理: %s", req)
            return False
        req_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._runtime.pending_confirms[(user_id, conversation_id, req_id)] = fut
        await queue.put({
            "type": "confirm",
            "req_id": req_id,
            "summary": getattr(req, "summary", "") or "",
            "tool_name": getattr(req, "tool_name", "") or "",
            "risk_level": getattr(req, "risk_level", "") or "",
            "cause": getattr(req, "cause", "") or "",
            "side_effects": getattr(req, "side_effects", None) or [],
            "params": _confirm_params_view(getattr(req, "params", None)),
        })
        try:
            return await asyncio.wait_for(
                fut, timeout=self._config.confirm_timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning("确认等待超时（%ss），按拒绝处理: %s",
                           getattr(self._config, "confirm_timeout_seconds", 300.0),
                           req)
            return False
        finally:
            self._runtime.pending_confirms.pop(
                (user_id, conversation_id, req_id), None)

    def confirm_callback(self, user_id: str, conversation_id: str):
        """构造绑定会话的确认回调（传给会话装配）。"""

        async def callback(req) -> bool:
            return await self._handle_confirm(user_id, conversation_id, req)
        return callback

    async def confirm(self, user_id: str, conversation_id: str, req_id: str,
                      approved: bool) -> dict:
        """回传确认决定（approved=true/false），唤醒等待中的 run。"""
        fut = self._runtime.pending_confirms.get(
            (user_id, conversation_id, req_id))
        if fut is None or fut.done():
            raise NotFoundError("确认请求不存在或已结算")
        fut.set_result(bool(approved))
        return {"status": "ok"}

    async def stream(self, user_id: str, task: str, conversation_id: str,
                     project_id: str | None, attachments: list[dict],
                     is_disconnected: Callable[[], Awaitable[bool]]
                     ) -> AsyncIterator[str]:
        """对话流：SSE 帧序列（token/tool/round/done）。"""
        task = task.strip()
        conversation_id = conversation_id.strip()
        project_id = project_id or None
        if not task or not conversation_id:
            raise RequestValidationError("task 与 conversation_id 必填")

        # 空闲驱逐：超过阈值的 agent 实例丢弃（下一请求从 DB 重建，回归安全）
        import time as _time
        now = _time.monotonic()
        for stale_key, last in list(self._runtime.agent_last_used.items()):
            if (now - last
                    > getattr(self._config, "agent_idle_evict_seconds", 1800.0)
                    and stale_key in self._runtime.agents):
                self._runtime.agents.pop(stale_key, None)
                self._runtime.agent_last_used.pop(stale_key, None)
                # 队列随 agent 一起丢弃：已死会话的队列留着只会无限堆积
                state._queues.pop((stale_key[0], stale_key[1]), None)

        # 附件：平台文件按 id 注入任务文本；本地副本只给沙箱一次性读取用。
        attachments = self._attachments.resolve(
            user_id, attachments, conversation_id)
        attachment_meta = self._attachments.meta(attachments)
        # 用户原话先留一份：标题与历史展示都只取原话
        user_task = task
        if attachments:
            lines = [
                f"{ATTACHMENT_HEADER}（用 kind + id 调 read_file/read_pdf；"
                "run_python / run_shell 里用 /corpus/uploads/ 下的沙箱路径）："
            ]
            for a in attachments:
                kind = "paper" if a.get("paper_id") else "file"
                obj_id = a.get("paper_id") or a.get("file_id") or ""
                sandbox = "/corpus/uploads/" + Path(a["path"]).name
                lines.append(
                    f"- {a['name']}（{a['size']} 字节，kind={kind}，id={obj_id}，"
                    f"沙箱路径={sandbox}）")
            task = "\n".join(lines) + "\n\n" + task

        key = (user_id, conversation_id, state.user_models.get(user_id))
        if key not in self._runtime.agents:
            built = self._agent_factory(
                user_id, conversation_id,
                self.confirm_callback(user_id, conversation_id), project_id)
            # 工厂可为同步或异步（真实装配是 async，测试替身是同步 lambda）
            self._runtime.agents[key] = (
                await built if asyncio.iscoroutine(built) else built)
            # 装配即快照固定开销基线（head 各块 + 工具 schema）
            try:
                snap = self._runtime.agents[key].context_usage()
                self._runtime.usage_baseline[
                    (user_id, state.user_models.get(user_id))] = {
                    "parts": {k: v for k, v in snap["parts"].items()
                              if k != "messages"},
                    "limit": snap["limit"],
                }
            except Exception:
                logger.debug("上下文用量基线快照失败", exc_info=True)
        agent = self._runtime.agents[key]
        self._runtime.agent_last_used[key] = now
        # 单用户并发配额：超限即拒绝（fail-closed，不排队饿死其他用户）
        if self._runtime.user_runs.get(user_id, 0) >= getattr(
                self._config, "per_user_run_limit", 3):
            raise TooManyRequestsError(
                "该账号并发任务已达上限，请等待进行中的任务完成")
        self._runtime.user_runs[user_id] = (
            self._runtime.user_runs.get(user_id, 0) + 1)

        async def stream_chat() -> AsyncIterator[str]:
            """把一轮 run 的事件桥接成 SSE 帧。"""
            queue: asyncio.Queue = asyncio.Queue()
            # 注册活动流：确认请求投递到这里（无活动流时确认按拒绝处理）
            self._runtime.active_queues[(user_id, conversation_id)] = queue

            def on_event(event) -> None:
                """线程安全地把 Agent 事件投进当前流的队列。"""
                # stream_callback 是同步回调（Agent 线程内直接调）：线程安全投递
                queue.put_nowait({
                    "type": str(getattr(event, "kind", "content")).replace(
                        "AgentEventKind.", "").lower(),
                    "text": getattr(event, "text", "") or "",
                    "agent_type": getattr(event, "agent_type", ""),
                    "tool_name": getattr(event, "tool_name", "") or "",
                    "completion": getattr(event, "completion", "") or "",
                    "duration_ms": getattr(event, "duration_ms", None),
                })

            async def run_task() -> str:
                """执行一轮 run，并在收尾时回填附件元数据。"""
                # 标题在 run 开始时就落库；用用户原话，不用注入清单
                await self._session.autotitle(
                    user_id, conversation_id, user_task)
                try:
                    # 全局并发闸（run 粒度）
                    async with self._runtime.llm_gate:
                        answer = await agent.run(task, stream_callback=on_event)
                    # 轮末整合：只 enqueue，防抖与游标推进由队列/DB 锁自理
                    consolidation = getattr(
                        agent, "_consolidation_queue", None)
                    if consolidation is not None:
                        try:
                            consolidation.enqueue()
                        except Exception:
                            logger.warning("整合入队失败（不影响本轮回答）",
                                           exc_info=True)
                    return answer
                finally:
                    # 用户消息此时已随 run 落盘：回填附件元数据
                    self._attachments.persist(
                        user_id, conversation_id, task, attachment_meta)

            run_handle: asyncio.Task | None = None

            async def watch_disconnect() -> None:
                """客户端断开 → 取消 run（复用取消级联）。"""
                while True:
                    if await is_disconnected():
                        if run_handle is not None:
                            run_handle.cancel()
                        return
                    await asyncio.sleep(0.3)

            async def drain() -> AsyncIterator[str]:
                """把队列事件转成 SSE 帧，并在 run 结束后补发收尾帧。"""
                nonlocal run_handle
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
                        yield (f"data: {json.dumps({'type': 'done', 'text': answer}, ensure_ascii=False)}\n\n")
                    except asyncio.CancelledError:
                        yield (f"data: {json.dumps({'type': 'done', 'cancelled': True}, ensure_ascii=False)}\n\n")
                    except Exception as e:
                        # 错误一律降级为文本：error 帧说明原因，done 帧恒发收尾
                        yield (f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n")
                        yield (f"data: {json.dumps({'type': 'done', 'errored': True}, ensure_ascii=False)}\n\n")
                    finally:
                        self._runtime.active_queues.pop(
                            (user_id, conversation_id), None)

            try:
                async for chunk in drain():
                    yield chunk
            finally:
                # 流结束清活动队列；并发配额归还
                if self._runtime.active_queues.get(
                        (user_id, conversation_id)) is queue:
                    self._runtime.active_queues.pop(
                        (user_id, conversation_id), None)
                self._runtime.user_runs[user_id] = max(
                    0, self._runtime.user_runs.get(user_id, 1) - 1)

        return stream_chat()

    async def flush_consolidations(self) -> None:
        """停服时 flush 整合队列。"""
        for q in list(state._queues.values()):
            try:
                await q.flush()
            except Exception as e:      # pragma: no cover
                logger.warning("停服整合 flush 失败（游标由 DB 兜底）: %r", e)
        state._queues.clear()
