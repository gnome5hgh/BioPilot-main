"""FastAPI 应用工厂：对话 SSE 流 + 健康检查。

SSE 桥接约定：
    - 事件帧：``data: {"type": "token"|"tool"|"round"|"done"|"error", ...}``
    - 流结束帧 type=done 恒发出（含异常路径）——客户端据此判断可复用连接。
    - 客户端断开（Request.is_disconnected）→ 取消 run（复用 Agent 的取消级联，
      与 REPL Ctrl-C 同路径），不留悬挂任务占会话运行锁。

装配策略：进程内字典按 (user_id, conversation_id) 缓存
Agent 实例，工厂函数 ``agent_factory`` 可注入替换（测试用 fake Agent 直打 S1 缝）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
from pathlib import Path

import yaml as yaml_mod

import uuid
from dataclasses import dataclass

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

#: 论文上传的单文件上限：超限直接拒绝，不把大文件整个读进内存
_PAPER_UPLOAD_LIMIT = 200 * 1024 * 1024


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
    # 确认等待上限（秒）：超时视为拒绝，计时在这里完成（不依赖 SSE 连接存活）
    confirm_timeout_seconds: float = 300.0


_db_instance = None


def yaml_path() -> pathlib.Path:
    """config.yaml 路径（工作区约定：仓库根）。"""
    return pathlib.Path.cwd() / "config.yaml"


def _shared_db():
    """适配层共享的 MemoryDB（懒建；标题更新等轻量 SQL 用）。"""
    global _db_instance
    if _db_instance is None:
        from biopilot.core.memory.storage.database import MemoryDB
        _db_instance = MemoryDB()
    return _db_instance


async def _autotitle(user_id: str, conversation_id: str, task: str) -> None:
    """首条任务生成会话标题：name 为空才设（不覆盖手动改名），取任务前 20 字。

    标题失败只记日志——它是对话的可读性增强，不影响主流程。
    """
    try:
        db = _shared_db()
        row = db.execute(
            "SELECT name FROM agent_state WHERE agent_id=? AND user_id=?",
            (conversation_id, user_id)).fetchone()
        if row is not None and row["name"] is None:
            title = task.strip().replace("\n", " ")[:20]
            db.execute("UPDATE agent_state SET name=? WHERE agent_id=? AND user_id=?",
                       (title, conversation_id, user_id))
    except Exception as e:      # pragma: no cover
        logger.warning("会话标题生成失败: %r", e)


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
    #: 全局并发闸（run 粒度在途上限；多用户总闸，单学生的批量派发占不满全部外部资源）
    llm_gate = asyncio.Semaphore(getattr(config, "llm_max_concurrency", 8))
    #: 单用户活跃 run 计数（防单用户占满并发）
    user_runs: dict[str, int] = {}
    #: agent 最后使用时刻（idle 驱逐依据）
    agent_last_used: dict[tuple[str, str], float] = {}
    #: 进行中的确认等待：(user_id, conversation_id, req_id) -> Future[bool]
    pending_confirms: dict[tuple[str, str, str], asyncio.Future] = {}
    #: 正在 run 的会话流队列（确认帧投到对应请求的流里）
    active_queues: dict[tuple[str, str], asyncio.Queue] = {}

    async def _handle_confirm(user_id: str, conversation_id: str, req) -> bool:
        """把确认请求推给浏览器并等待决定；超时/无活动流按拒绝处理。

        Args:
            user_id: 归属用户。
            conversation_id: 会话标识。
            req: ConfirmRequired（策略引擎产出）。

        Returns:
            True=用户批准；False=拒绝/超时/无活动流。
        """
        queue = active_queues.get((user_id, conversation_id))
        if queue is None:
            logger.warning("确认请求无活动流可投递，按拒绝处理: %s", req)
            return False
        req_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        pending_confirms[(user_id, conversation_id, req_id)] = fut
        await queue.put({
            "type": "confirm",
            "req_id": req_id,
            "summary": getattr(req, "summary", "") or "",
            "tool_name": getattr(req, "tool_name", "") or "",
        })
        try:
            return await asyncio.wait_for(fut, timeout=config.confirm_timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning("确认等待超时（%ss），按拒绝处理: %s",
                           getattr(config, "confirm_timeout_seconds", 300.0), req)
            return False
        finally:
            pending_confirms.pop((user_id, conversation_id, req_id), None)

    def _confirm_callback(user_id: str, conversation_id: str):
        """构造绑定会话的确认回调（传给会话装配）。"""

        async def callback(req) -> bool:
            return await _handle_confirm(user_id, conversation_id, req)
        return callback

    @app.on_event("shutdown")
    async def _flush_consolidations() -> None:
        """停服时把活跃会话的整合队列 flush（游标推进走 DB 锁，多进程安全）。"""
        for q in _queues:
            try:
                await q.flush()
            except Exception as e:      # pragma: no cover
                logger.warning("停服整合 flush 失败（游标由 DB 兜底）: %r", e)
        _queues.clear()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/chat/confirm")
    async def chat_confirm(
        body: dict,
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        """回传确认决定（approved=true/false），唤醒等待中的 run。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        req_id = (body or {}).get("req_id", "")
        approved = bool((body or {}).get("approved", False))
        fut = pending_confirms.get((x_user_id, (body or {}).get("conversation_id", ""), req_id))
        if fut is None or fut.done():
            raise HTTPException(status_code=404, detail="确认请求不存在或已结算")
        fut.set_result(approved)
        return {"status": "ok"}

    @app.post("/store/skills/{name}/toggle")
    async def skill_toggle(
        name: str, body: dict, x_user_id: str | None = Header(default=None),
    ) -> dict:
        """技能启用/禁用：写 skills.lock.json（原子写+文件锁，fail-closed 校验）。

        ADMIN 专属（管理动作）；enabled=false 时 registry 扫描期跳过该技能。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        enabled = bool((body or {}).get("enabled", True))

        # 读写走 skills 体系自己的 lock 助手：信封带 schema 版本、原子替换、
        # 排序稳定——裸 JSON 读写会把信封抹掉，下一次任何 lock 消费方直接 fail-closed
        import fcntl
        from biopilot.core.skills.services.install import (
            _save_lock, lock_path as _lock_path)
        from biopilot.core.skills import load_lock
        pf_dir = Path.cwd() / ".biopilot"
        lock_fp = open(_lock_path(pf_dir), "a+")
        try:
            fcntl.flock(lock_fp, fcntl.LOCK_EX)
            skills = (load_lock(pf_dir)
                      if _lock_path(pf_dir).stat().st_size > 0 else {})
            entry = skills.get(name, {})
            entry["enabled"] = enabled
            skills[name] = entry
            _save_lock(pf_dir, skills)
        finally:
            fcntl.flock(lock_fp, fcntl.LOCK_UN)
            lock_fp.close()
        return {"status": "ok", "name": name, "enabled": enabled}

    @app.get("/store/skills")
    async def store_skills(x_user_id: str | None = Header(default=None)) -> dict:
        """技能列表：.biopilot/skills 真数据（名称/版本/描述/启用态）。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.core.skills import SkillRegistry, load_lock
        pf_dir = Path.cwd() / ".biopilot"
        lock = load_lock(pf_dir) if (pf_dir / "skills.lock.json").exists() else {}
        reg = SkillRegistry(str(pf_dir / "skills") if (pf_dir / "skills").is_dir() else None,
                            disabled={n for n, e in lock.items() if not e.get("enabled", True)})
        skills = [{"name": n,
                   "version": ((reg.get_skill(n).metadata or {}).get("version", "")
                               if reg.get_skill(n) else ""),
                   "description": (reg.get_skill(n).description[:120]
                                   if reg.get_skill(n) else ""),
                   "enabled": lock.get(n, {}).get("enabled", True)}
                  for n in reg.list_skills()]
        return {"skills": skills}

    @app.get("/chat/history")
    async def chat_history(
        conversation_id: str = "",
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        """取一段会话的可见历史（user/assistant 两条腿，按时间正序）。

        会话列表点击回续时前端用它回放消息；tool/system 行不外露——那是
        引擎的内部轨迹，不是对话内容。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        if not conversation_id:
            return {"messages": []}
        db = _shared_db()
        rows = db.execute(
            "SELECT role, content, created_at FROM messages"
            " WHERE agent_id=? AND user_id=? AND role IN ('user','assistant')"
            " AND content IS NOT NULL AND content != ''"
            " ORDER BY seq", (conversation_id, x_user_id)).fetchall()
        return {"messages": [dict(r) for r in rows]}

    @app.delete("/chat/session")
    async def chat_session_delete(
        conversation_id: str = "", x_user_id: str | None = Header(default=None),
    ) -> dict:
        """删除一个会话：消息行 + agent_state 行（归属双条件）。

        进程内缓存的 Agent 实例一并弹出（会话 id 是 uuid，理论不会复用，
        弹缓存是防手滑复用旧窗口的兜底）。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        if not conversation_id:
            raise HTTPException(status_code=422, detail="缺少 conversation_id")
        db = _shared_db()
        db.execute("DELETE FROM messages WHERE agent_id=? AND user_id=?",
                   (conversation_id, x_user_id))
        gone = db.execute("DELETE FROM agent_state WHERE agent_id=? AND user_id=?",
                          (conversation_id, x_user_id))
        agents.pop((x_user_id, conversation_id, user_models.get(x_user_id)), None)
        agent_last_used.pop((x_user_id, conversation_id), None)
        if gone == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
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
        project_id = (body or {}).get("project_id") or None
        if not task or not conversation_id:
            raise HTTPException(status_code=422, detail="task 与 conversation_id 必填")

        # 空闲驱逐：超过阈值的 agent 实例丢弃（下一请求从 DB 重建，回归安全）
        import time as _time
        now = _time.monotonic()
        for stale_key, last in list(agent_last_used.items()):
            if now - last > getattr(config, "agent_idle_evict_seconds", 1800.0) and stale_key in agents:
                agents.pop(stale_key, None)
                agent_last_used.pop(stale_key, None)

        key = (x_user_id, conversation_id, user_models.get(x_user_id))
        if key not in agents:
            built = agent_factory(x_user_id, conversation_id,
                                  _confirm_callback(x_user_id, conversation_id),
                                  project_id)
            # 工厂可为同步或异步（真实装配是 async，测试替身是同步 lambda）
            agents[key] = await built if asyncio.iscoroutine(built) else built
        agent = agents[key]
        agent_last_used[key] = now
        # 单用户并发配额：超限即拒绝（fail-closed，不排队饿死其他用户）
        if user_runs.get(x_user_id, 0) >= getattr(config, "per_user_run_limit", 3):
            raise HTTPException(
                status_code=429,
                detail="该账号并发任务已达上限，请等待进行中的任务完成")
        user_runs[x_user_id] = user_runs.get(x_user_id, 0) + 1

        async def stream_chat():
            queue: asyncio.Queue = asyncio.Queue()
            # 注册活动流：确认请求投递到这里（无活动流时确认按拒绝处理）
            active_queues[(x_user_id, conversation_id)] = queue

            def on_event(event) -> None:
                # stream_callback 是同步回调（Agent 线程内直接调）：线程安全投递
                queue.put_nowait({
                    "type": getattr(event, "kind", "token"),
                    "text": getattr(event, "text", "") or "",
                    "agent_type": getattr(event, "agent_type", ""),
                })

            async def run_task() -> str:
                # 全局并发闸（run 粒度）：多用户在途 run 总上限，批量派发占不满外部资源
                async with llm_gate:
                    answer = await agent.run(
                        task, stream_callback=on_event) if _accepts_stream(
                        agent.run) else await agent.run(task)
                await _autotitle(x_user_id, conversation_id, task)
                # 轮末整合：与 REPL 同语义（一轮对话结束 → 沉淀进记忆）；
                # 只 enqueue，防抖与游标推进由队列/DB 锁自理
                queue = getattr(agent, "_consolidation_queue", None)
                if queue is not None:
                    try:
                        queue.enqueue()
                    except Exception:
                        logger.warning("整合入队失败（不影响本轮回答）",
                                       exc_info=True)
                return answer

            # run 任务句柄挂流作用域：断开监视与 drain 共享（此前是 drain 局部变量，
            # 断开分支引用它会 NameError，run 取消失效）
            run_handle: asyncio.Task | None = None

            async def watch_disconnect() -> None:
                """客户端断开 → 取消 run（复用取消级联，与 REPL Ctrl-C 同路径）。"""
                while True:
                    if await request.is_disconnected():
                        if run_handle is not None:
                            run_handle.cancel()
                        return
                    await asyncio.sleep(0.3)

            async def drain():
                nonlocal run_handle
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
                    finally:
                        active_queues.pop((x_user_id, conversation_id), None)

            try:
                async for chunk in drain():
                    yield chunk
            finally:
                # 流结束清活动队列（此后确认请求无投递目标 → 按拒绝处理）；
                # 并发配额归还——只有还挂在缓存里的 run 才算「在途」
                if active_queues.get((x_user_id, conversation_id)) is queue:
                    active_queues.pop((x_user_id, conversation_id), None)
                user_runs[x_user_id] = max(0, user_runs.get(x_user_id, 1) - 1)
            return

        return StreamingResponse(stream_chat(), media_type="text/event-stream")

    # 设置端点（ADMIN 专属在 Java 层守卫）：意图开关/确认档位/沙箱配置的语义子集
    @app.get("/settings")
    async def settings_get(x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        return {"intent_enabled": cfg.intent.enabled,
                "confirm_above": cfg.runtime.confirm_above,
                "models": cfg.runtime.models}

    @app.get("/models")
    async def models_list(x_user_id: str | None = Header(default=None)) -> dict:
        """可选模型清单：主模型 + runtime.models 配置条目（不回传 key）。

        空配置时退化为只展示主模型——前端据此隐藏切换器。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        items = [{"name": m.get("name") or m.get("model", ""),
                  "model": m.get("model", ""),
                  "current": False}
                 for m in cfg.runtime.models]
        items.insert(0, {"name": "默认主模型", "model": cfg.llm.model, "current": True})
        return {"models": items,
                "selected": user_models.get(x_user_id),
                "base_model": cfg.llm.model}

    @app.post("/models/select")
    async def models_select(body: dict, x_user_id: str | None = Header(default=None)) -> dict:
        """会话级模型选择：本用户后续 run 用所选模型（agent 缓存按模型分键）。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        name = (body or {}).get("name", "")
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        if name and name != "默认主模型":
            known = any((m.get("name") or m.get("model")) == name for m in cfg.runtime.models)
            if not known:
                raise HTTPException(status_code=422, detail=f"未知模型：{name}")
            user_models[x_user_id] = name
        else:
            user_models[x_user_id] = None    # 回到主模型
        return {"status": "ok", "selected": user_models.get(x_user_id)}

    #: 设置端点可写的键 → config.yaml 里的嵌套落点（覆盖链：schema 默认 ← config.yaml ← env）。
    #: 只开语义子集，凭据类字段永不经此通道。
    _SETTING_PATHS = {
        "intent_enabled": ("intent", "enabled"),
        "confirm_above": ("runtime", "confirm_above"),
    }

    @app.post("/settings")
    async def settings_set(body: dict, x_user_id: str | None = Header(default=None)) -> dict:
        """ADMIN 设置写入：把白名单键合并进 config.yaml 的嵌套覆盖结构。

        生效语义是「下一 run」——引擎在 run 启动时读一次配置快照，本端点只负责
        把覆盖值真正落盘（此前实现只回显 applied、从未合并写入，保存是空操作）。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        cfg_path = yaml_path()
        overrides = {k: v for k, v in (body or {}).items() if k in _SETTING_PATHS}
        applied = []
        if overrides:
            existing = {}
            if cfg_path.exists():
                existing = yaml_mod.safe_load(cfg_path.read_text()) or {}
            for key, value in overrides.items():
                node = existing
                for seg in _SETTING_PATHS[key][:-1]:
                    node = node.setdefault(seg, {})
                    if not isinstance(node, dict):
                        raise HTTPException(status_code=422,
                                            detail=f"配置结构冲突：{key}")
                node[_SETTING_PATHS[key][-1]] = value
                applied.append(key)
            with open(cfg_path, "w") as fh:
                yaml_mod.safe_dump(existing, fh, allow_unicode=True)
        return {"status": "ok", "applied": applied}

    # 删户两阶段：标记 → 等活动清零 → 物理删除（幂等）
    @app.post("/admin/users/{target_id}/mark-deleting")
    async def mark_deleting(target_id: str, x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        db.execute("UPDATE agent_state SET user_id=CONCAT('deleting:', user_id)"
                   " WHERE user_id=? AND user_id NOT LIKE 'deleting:%'", (target_id,))
        return {"status": "marked"}

    @app.post("/admin/users/{target_id}/purge")
    async def purge_user(target_id: str, x_user_id: str | None = Header(default=None)) -> dict:
        """物理清除该用户的全部引擎数据（幂等，可重复执行）。

        agent_state 在 mark-deleting 阶段被改名为 `deleting:<uid>`，这里两种
        形态都清；其余表从未改名，按原 uid 删。无论是否先走过 mark 都收敛。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        for table in ("messages", "blocks", "block_history", "papers", "documents"):
            db.execute(f"DELETE FROM {table} WHERE user_id=?", (target_id,))
        db.execute("DELETE FROM agent_state WHERE user_id=?"
                   " OR user_id LIKE CONCAT('deleting:', ?)", (target_id, target_id))
        return {"status": "purged", "user_id": target_id}

    # 终端 WebSocket：PTY 跑 biopilot REPL（用户自己的终端，非 agent 工具）。
    # fail-closed：缺 X-User-Id 直接拒连（与 HTTP 端点同一信任边界）；
    # 子进程是该用户的 biopilot REPL（同库、带确认中间件）——绝不给裸宿主 shell。
    @app.websocket("/ws/terminal")
    async def ws_terminal(ws: WebSocket):
        import os as _os
        import pty as _pty
        import sys as _sys
        x_user_id = ws.headers.get("x-user-id", "")
        if not x_user_id:
            await ws.close(code=1008, reason="缺少 X-User-Id 请求头")
            return
        await ws.accept()
        master, slave = _pty.openpty()
        env = _os.environ.copy()
        env["BIOPILOT_MEMORY_MYSQL_DSN"] = (
            _os.environ.get("BIOPILOT_MEMORY_MYSQL_DSN", "mysql://root@127.0.0.1:3306/biopilot"))
        proc = await asyncio.create_subprocess_exec(
            _sys.executable, "-m", "biopilot", "--resume",
            stdin=slave, stdout=slave, stderr=slave, env=env,
            cwd=str(pathlib.Path.cwd()))
        _os.close(slave)

        async def pump_out():
            """PTY 输出 → WebSocket 文本帧。"""
            loop = asyncio.get_event_loop()
            while True:
                data = await loop.run_in_executor(None, _os.read, master, 4096)
                if not data:
                    break
                await ws.send_text(data.decode("utf-8", errors="replace"))

        async def pump_in():
            """WebSocket 文本帧 → PTY 输入。"""
            while True:
                msg = await ws.receive_text()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _os.write, master, msg.encode())

        try:
            await asyncio.gather(pump_out(), pump_in())
        except Exception:
            pass
        finally:
            proc.terminate()

    _paper_endpoints(app)
    # 索引触发：按用户域重建 RAG collection（RAGService user_domain）
    # 每用户重建 singleflight：重建进行中时重复触发直接返回（防并发「先删后建」互删）
    reindex_running: set[str] = set()

    @app.post("/kb/reindex")
    async def kb_reindex(x_user_id: str | None = Header(default=None)) -> dict:
        """按用户域触发全量重建：后台线程跑 index_all（嵌入耗时可能数十分钟），
        本端点立即返回；进度用 GET /kb/status 看 indexed 计数爬升。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        if x_user_id in reindex_running:
            return {"status": "already-running"}
        from biopilot.core.rag.services.rag_service import get_rag_service
        from biopilot.config import BioPilotConfig
        from biopilot.core.rag.storage.image_store import MinioImageStore
        cfg = BioPilotConfig.from_env()
        svc = get_rag_service(cfg, user_domain=x_user_id)
        store = MinioImageStore(cfg.rag.storage.minio)
        db = _shared_db()
        reindex_running.add(x_user_id)

        def _job() -> None:
            try:
                # 平台论文的原文在 MinIO、元数据在 papers 表：同步镜像后走
                # 本域 index_all 管线；成功的行置 indexed=1（进度看 /kb/status）
                svc.index_user_papers(x_user_id, db, store)
            finally:
                reindex_running.discard(x_user_id)

        asyncio.get_running_loop().create_task(asyncio.to_thread(_job))
        return {"status": "started"}

    # KB 展示：索引状态快照（papers 已索引计数 + collection 命名）
    @app.get("/kb/status")
    async def kb_status(x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        total = db.execute("SELECT COUNT(*) AS c FROM papers WHERE user_id=?",
                           (x_user_id,)).fetchone()["c"]
        indexed = db.execute("SELECT COUNT(*) AS c FROM papers WHERE user_id=? AND indexed=1",
                             (x_user_id,)).fetchone()["c"]
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        collection = cfg.rag.storage.collection + ("" if x_user_id == "local" else f"_{x_user_id}")
        return {"total_papers": total, "indexed": indexed,
                "collection": collection, "recipe": cfg.rag.storage.collection}

    _doc_endpoints(app)
    return app


def _accepts_stream(run_callable) -> bool:
    """判断 run 是否接受 stream_callback 参数（fake Agent 可能没有）。"""
    import inspect
    try:
        return "stream_callback" in inspect.signature(run_callable).parameters
    except (TypeError, ValueError):
        return False


async def _default_agent_factory(user_id: str, conversation_id: str,
                                 confirm_callback=None, project_id: str | None = None):
    # 模型选择读模块级 user_models（端点写入）——不进工厂签名，注入替身契约不变
    """真实装配：委托 assembly 的 web 会话装配（与 REPL 同一套对象图）。

    确认回调与项目归属原样透传——确认走 SSE 往返、project_id 进 agent_state。
    """
    from biopilot.cli.services.assembly import assemble_web_session
    session = await assemble_web_session(user_id, conversation_id,
                                         confirm_callback=confirm_callback,
                                         project_id=project_id,
                                         model_name=user_models.get(user_id))
    # 整合队列两处挂账：agent 实例上（每轮收尾 enqueue）+ 全局集合（停服 flush；
    # 游标推进走 DB 锁，多进程安全）
    session.agent._consolidation_queue = session.consolidation_queue
    _queues.append(session.consolidation_queue)
    return session.agent


#: 全部活跃会话的整合队列（on_shutdown 时统一 flush）
_queues: list = []
#: 会话级模型选择（user -> model 名；None 用默认主模型）
user_models: dict[str, str | None] = {}


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


def _paper_store():
    """论文对象的存取器：与图表原图共用同一 MinIO 连接配置与 bucket。

    独立成模块级工厂是为了测试可注入（论文上传测试换内存替身）。
    """
    from biopilot.config import BioPilotConfig
    from biopilot.core.rag.storage.image_store import MinioImageStore
    return MinioImageStore(BioPilotConfig.from_env().rag.storage.minio)


def _sanitize_paper_filename(name: str | None) -> str:
    """把上传文件名收敛成安全的对象键尾段：剥掉路径部分与控制字符。

    Args:
        name: 浏览器报来的原始文件名（可能带路径、可能为 None）。

    Returns:
        str: 只含文件名主体的安全字符串；剥完为空（如 ".."）时回退固定名。
    """
    import re
    base = pathlib.PurePosixPath(name or "").name
    cleaned = re.sub(r"[\x00-\x1f\\/]", "_", base).strip("_ ")
    return cleaned or "paper.pdf"


def _paper_endpoints(app: FastAPI) -> None:
    """论文目录端点：上传/登记/列表/删除，元数据在 papers 表、原文在 OSS。"""
    from biopilot.tools.papers import register_paper, list_papers, remove_paper

    # 上传路由必须先于 /papers/{paper_id} 声明，否则 "upload" 会被路径参数吞掉
    @app.post("/papers/upload")
    async def papers_upload(
        file: UploadFile,
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        """接收浏览器上传的论文原文：对象先落 OSS，成功后才写元数据行（失败留孤儿对象，
        不留死行）。

        标题恒为空串——标题只来自解析器出口，绝不回退到 PDF 文件名。

        Args:
            file: 浏览器 multipart 上传的论文文件（PDF）。
            x_user_id: 内网信任头（SpringBoot 注入的登录用户 id）。

        Returns:
            dict: status/id/oss_key。

        Raises:
            HTTPException: 缺头 403；空内容 422；超限 413；对象存储不可用 502。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        data = await file.read()
        if not data:
            raise HTTPException(status_code=422, detail="上传内容为空")
        if len(data) > _PAPER_UPLOAD_LIMIT:
            raise HTTPException(status_code=413, detail="文件超过大小上限")
        paper_id = uuid.uuid4().hex
        oss_key = (f"users/{x_user_id}/papers/{paper_id}/"
                   f"{_sanitize_paper_filename(file.filename)}")
        if not _paper_store().put_file(oss_key, data,
                                       file.content_type or "application/pdf"):
            raise HTTPException(status_code=502, detail="对象存储不可用，上传失败")
        register_paper(_shared_db(), x_user_id, paper_id, "", oss_key, len(data))
        return {"status": "ok", "id": paper_id, "oss_key": oss_key}

    @app.post("/papers/{paper_id}")
    async def papers_register(
        paper_id: str, body: dict,
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        oss_key = (body or {}).get("oss_key", "")
        # OSS 写围栏：登记的对象键必须落在本人前缀下（防登记/删除他人对象）
        if not oss_key.startswith(f"users/{x_user_id}/"):
            raise HTTPException(status_code=422,
                                detail="oss_key 必须以 users/<本人>/ 开头")
        db = _shared_db()
        register_paper(db, x_user_id, paper_id,
                       (body or {}).get("title", ""),
                       oss_key,
                       int((body or {}).get("size_bytes", 0)))
        return {"status": "ok"}

    @app.get("/papers")
    async def papers_list(x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        return {"papers": list_papers(_shared_db(), x_user_id)}

    @app.delete("/papers/{paper_id}")
    async def papers_delete(
        paper_id: str, x_user_id: str | None = Header(default=None),
    ) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        oss_key = remove_paper(_shared_db(), x_user_id, paper_id)
        if oss_key is None:
            raise HTTPException(status_code=404, detail="论文不存在")
        # 删除方向：行先行、对象随后；对象删除失败只留孤儿，可后台按前缀对账清扫
        _paper_store().remove(oss_key)
        return {"status": "ok", "oss_key": oss_key}


def _doc_endpoints(app: FastAPI) -> None:
    """文档编辑器端点：markdown 文档的 CRUD（内容行存，OSS 留同步口）。"""
    from biopilot.core.memory.storage.database import MemoryDB as _MDB

    @app.get("/documents")
    async def documents_list(x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        rows = db.execute("SELECT id, name, updated_at FROM documents"
                          " WHERE user_id=? ORDER BY seq DESC", (x_user_id,)).fetchall()
        return {"documents": [dict(r) for r in rows]}

    @app.post("/documents")
    async def documents_create(body: dict, x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from datetime import datetime, timezone
        db = _shared_db()
        doc_id = uuid.uuid4().hex
        name = (body or {}).get("name", "新文档.md")
        content = (body or {}).get("content", "")
        db.execute("INSERT INTO documents (id, user_id, name, content, updated_at)"
                   " VALUES (?,?,?,?,?)",
                   (doc_id, x_user_id, name, content,
                    datetime.now(timezone.utc).isoformat()))
        return {"status": "ok", "id": doc_id}

    @app.get("/documents/{doc_id}")
    async def documents_get(doc_id: str, x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        row = db.execute("SELECT id, name, content, updated_at FROM documents"
                         " WHERE id=? AND user_id=?", (doc_id, x_user_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        return dict(row)

    @app.put("/documents/{doc_id}")
    async def documents_save(
        doc_id: str, body: dict, x_user_id: str | None = Header(default=None),
    ) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from datetime import datetime, timezone
        db = _shared_db()
        db.execute("UPDATE documents SET content=?, updated_at=? WHERE id=? AND user_id=?",
                   ((body or {}).get("content", ""), datetime.now(timezone.utc).isoformat(),
                    doc_id, x_user_id))
        return {"status": "ok"}

    @app.get("/literature/search")
    async def literature_search(
        q: str = "", x_user_id: str | None = Header(default=None),
    ) -> dict:
        """文献搜索（PubMed E-utilities，AI 搜索走 agent 主链路）。"""
        if not x_user_id or not q.strip():
            return {"results": []}
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient(timeout=10) as hc:
                r = await hc.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                                 params={"db": "pubmed", "term": q, "retmax": 10,
                                         "retmode": "json"})
                ids = r.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return {"results": []}
            async with _httpx.AsyncClient(timeout=10) as hc:
                r = await hc.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                                 params={"db": "pubmed", "id": ",".join(ids),
                                         "retmode": "json"})
                result = r.json().get("result", {})
            out = [{"id": uid, "title": v.get("title", ""),
                    "journal": v.get("source", ""), "pubdate": v.get("pubdate", "")}
                   for uid, v in result.items() if uid != "uids"]
            return {"results": out}
        except Exception as e:
            logger.warning("PubMed 搜索失败: %r", e)
            return {"results": [], "error": str(e)}
