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

import yaml as yaml_mod

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
    #: 全局 LLM 在途并发闸（多用户总闸：单学生的批量派发占不满全部外部资源）
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

    @app.get("/store/experts")
    async def store_experts(x_user_id: str | None = Header(default=None)) -> dict:
        """专家列表：读 agents 插件真数据（名称/描述/版本）。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.core.agent import AgentRegistry
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        agents_dir = (cfg.runtime.agents_dir
                      if Path(cfg.runtime.agents_dir).is_dir()
                      else str(Path(__file__).resolve().parents[2] / "agents"))
        registry = AgentRegistry(agents_dir)
        experts = []
        for name in registry.list_agents():
            c = registry.get_config(name)
            experts.append({"name": name, "description": c.system_prompt[:120],
                            "tools_count": len(c.tools)})
        return {"experts": experts}

    @app.post("/store/skills/{name}/toggle")
    async def skill_toggle(
        name: str, body: dict, x_user_id: str | None = Header(default=None),
    ) -> dict:
        """技能启用/禁用：写 skills.lock.json（原子写+文件锁，fail-closed 校验）。

        ADMIN 专属（管理动作）；enabled=false 时 registry 扫描期跳过该技能。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        enabled = bool((body or {}).get("enabled", True))

        pf_dir = Path.cwd() / ".biopilot"
        lock_path = pf_dir / "skills.lock.json"
        # 原子写：临时文件 + os.replace（并发写不撕裂）
        import fcntl
        import os as _os
        import tempfile
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fp = open(lock_path, "a+")
        try:
            fcntl.flock(lock_fp, fcntl.LOCK_EX)
            import json as _json
            lock = _json.loads(lock_fp.read_text()) if lock_path.stat().st_size > 0 else {}
            entry = lock.get(name, {})
            entry["enabled"] = enabled
            if "version" not in entry:
                entry["version"] = "0.0.0"
            lock[name] = entry
            fd, tmp = tempfile.mkstemp(dir=str(lock_path.parent))
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(lock, f, ensure_ascii=False, indent=2)
            _os.replace(tmp, lock_path)
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
                   "version": reg.get_skill(n).version if reg.get_skill(n) else "",
                   "description": (reg.get_skill(n).description[:120]
                                   if reg.get_skill(n) else ""),
                   "enabled": lock.get(n, {}).get("enabled", True)}
                  for n in reg.list_skills()]
        return {"skills": skills}

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
                answer = await agent.run(
                    task, stream_callback=on_event) if _accepts_stream(
                    agent.run) else await agent.run(task)
                await _autotitle(x_user_id, conversation_id, task)
                return answer

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
                    finally:
                        active_queues.pop((x_user_id, conversation_id), None)

            async for chunk in drain():
                yield chunk

            # 流结束清活动队列（此后确认请求无投递目标 → 按拒绝处理）
            active_queues.pop((x_user_id, conversation_id), None)
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

    @app.post("/settings")
    async def settings_set(body: dict, x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        # 语义子集写 config.yaml（覆盖链的最后一层：config.py ← config.yaml ← env）
        # 只写白名单键，不碰凭据
        import yaml as _yaml
        cfg_path = yaml_path()
        allowed = {"intent_enabled", "confirm_above"}
        overrides = {k: v for k, v in (body or {}).items() if k in allowed}
        if overrides:
            existing = {}
            if cfg_path.exists():
                existing = yaml_mod.safe_load(cfg_path.read_text()) or {}
            yaml_mod.safe_dump(existing, open(cfg_path, "w"), allow_unicode=True)
        return {"status": "ok", "applied": list(overrides)}

    # 删户两阶段（P0-4）：标记 → 等活动清零 → 物理删除（幂等）
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
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        for table in ("messages", "blocks", "block_history", "papers", "documents"):
            db.execute(f"DELETE FROM {table} WHERE user_id=?", (target_id,))
        db.execute("DELETE FROM agent_state WHERE user_id=?", (target_id,))
        return {"status": "purged", "user_id": target_id}

    _paper_endpoints(app)
    _doc_endpoints(app)
    return app


def _accepts_stream(run_callable) -> bool:
    """判断 run 是否接受 stream_callback 参数（fake Agent 可能没有）。"""
    import inspect
    try:
        return "stream_callback" in inspect.signature(run_callable).parameters
    except (TypeError, ValueError):
        return False


async def _default_agent_factory(user_id: str, conversation_id: str):
    """真实装配：委托 assembly 的 web 会话装配（与 REPL 同一套对象图）。"""
    from biopilot.cli.services.assembly import assemble_web_session
    session = await assemble_web_session(user_id, conversation_id)
    # 整合队列挂到全局收尾集合：停服时 flush（游标推进走 DB 锁，多进程安全）
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


def _paper_endpoints(app: FastAPI) -> None:
    """论文目录端点（工单 16）：登记/列表/删除，元数据在 papers 表。"""
    from biopilot.tools.papers import register_paper, list_papers, remove_paper

    @app.post("/papers/{paper_id}")
    async def papers_register(
        paper_id: str, body: dict,
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        db = _shared_db()
        register_paper(db, x_user_id, paper_id,
                       (body or {}).get("title", ""),
                       (body or {}).get("oss_key", ""),
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
        return {"status": "ok", "oss_key": oss_key}


def _doc_endpoints(app: FastAPI) -> None:
    """文档编辑器端点（工单 19）：markdown 文档的 CRUD（内容行存，OSS 留同步口）。"""
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
