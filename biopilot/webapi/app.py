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

from biopilot.webapi.shell import ShellManager
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

#: 附件清单注入任务文本时使用的固定抬头：历史回放据此把注入块从展示正文中剥掉。
_ATTACHMENT_HEADER = "【附件】以下数据文件已就位"

#: 设置端点可写的键 → config.yaml 里的嵌套落点（覆盖链：schema 默认 ← config.yaml ← env）。
#: 只开语义子集，凭据类字段永不经此通道。
_SETTING_PATHS = {
    "intent_enabled": ("intent", "enabled"),
    "confirm_above": ("runtime", "confirm_above"),
}


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


_platform_instance = None


def _platform_client():
    """Java 平台内部端点客户端（懒建单例）。"""
    global _platform_instance
    if _platform_instance is None:
        from biopilot.common.platform import make_platform_client
        from biopilot.config import BioPilotConfig
        _platform_instance = make_platform_client(BioPilotConfig.from_env())
    return _platform_instance


def _safe_component(value: str) -> str:
    """把用户/会话/文件名归一化成可安全拼进本地路径的片段。

    只处理路径分隔符与 ``..``，保留中文等正常文件名字符；空值回退 ``unknown``。

    Args:
        value: 原始片段。

    Returns:
        不含路径分隔符与上跳片段的字符串。
    """
    text = str(value or "").replace("\\", "_").replace("/", "_")
    text = text.replace("\x00", "").strip()
    while ".." in text:
        text = text.replace("..", "_")
    return text or "unknown"


#: 确认框里不展示取值的参数名（凭证类一律脱敏，避免用户在看确认框时泄露密钥）
_SECRET_PARAM_KEYS = {"api_key", "apikey", "token", "password", "secret", "access_key", "secret_key"}


def _confirm_params_view(params) -> dict:
    """把工具入参整理成确认框可展示的扁平字典。

    只保留能帮助用户判断「这次要做什么」的信息：长文本截断，凭证类脱敏。
    展示的是用户自己的调用，不做内容审核——审核归内容防护中间件。

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


async def _autotitle(user_id: str, conversation_id: str, task: str) -> None:
    """首条任务生成会话标题：name 为空才设（不覆盖手动改名），取任务前 20 字。

    标题失败只记日志——它是对话的可读性增强，不影响主流程。
    """
    try:
        db = _shared_db()
        row = db.execute(
            "SELECT name FROM bio_agent_state WHERE agent_id=? AND user_id=?",
            (conversation_id, user_id)).fetchone()
        if row is not None and row["name"] is None:
            title = task.strip().replace("\n", " ")[:20]
            db.execute("UPDATE bio_agent_state SET name=? WHERE agent_id=? AND user_id=?",
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
    #: 网页终端的持久 shell：一个用户一条，跨会话/面板开关复用
    shell_manager = ShellManager()
    app.state.shell_manager = shell_manager
    agents: dict[tuple[str, str], object] = {}
    #: 全局并发闸（run 粒度在途上限；多用户总闸，单学生的批量派发占不满全部外部资源）
    llm_gate = asyncio.Semaphore(getattr(config, "llm_max_concurrency", 8))
    #: 单用户活跃 run 计数（防单用户占满并发）
    user_runs: dict[str, int] = {}
    #: agent 最后使用时刻（idle 驱逐依据）
    agent_last_used: dict[tuple[str, str], float] = {}
    #: 上下文用量的固定开销基线：(user_id, model) -> {parts, limit}。Agent 装配好
    #  即快照一份（此时窗口为空，parts 恰好只含 head 各块 + 工具 schema）；会话
    #  未装配（新会话/进程重启/空闲驱逐）时按基线 + DB 消息估算回答案指示器数据
    usage_baseline: dict[tuple[str, str], dict] = {}
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
            # 前端此前只能拿到工具名，用户实际是在「不知道要写哪个文件」的情况下点批准。
            # 这里把策略引擎已掌握的风险、副作用、触发原因与入参一并下行，确认框据此
            # 说明「这次问的是哪件事」。
            "summary": getattr(req, "summary", "") or "",
            "tool_name": getattr(req, "tool_name", "") or "",
            "risk_level": getattr(req, "risk_level", "") or "",
            "cause": getattr(req, "cause", "") or "",
            "side_effects": getattr(req, "side_effects", None) or [],
            "params": _confirm_params_view(getattr(req, "params", None)),
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
        """停服时 flush 整合队列，并结束所有网页终端 shell。"""
        for q in _queues:
            try:
                await q.flush()
            except Exception as e:      # pragma: no cover
                logger.warning("停服整合 flush 失败（游标由 DB 兜底）: %r", e)
        _queues.clear()
        reaper = getattr(app.state, "shell_reaper", None)
        if reaper is not None:
            reaper.cancel()
        try:
            await shell_manager.shutdown()
        except Exception:
            logger.warning("停服结束终端 shell 失败", exc_info=True)

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

    def _resolve_attachments(x_user_id: str, attachments: list[dict],
                             conversation_id: str) -> list[dict]:
        """把消息引用的附件落成本地文件并返回清单（发给模型的元数据行）。

        身份与字节都由 Java 解析：这里只传 ``(kind, id)``，拿回字节与服务器侧
        元数据。body 里的 oss_key/name/size 一律忽略——它们来自浏览器，不能作为
        归属依据（否则可以把别人的 oss_key 塞进来读走别人的文件）。

        本地副本落到 ``users/<uid>/uploads/<会话>/``，沙箱按会话挂载该目录；
        路径片段先归一化，防客户端传入 ``..`` 写出上传目录。

        Args:
            x_user_id: 归属用户。
            attachments: 消息体里的 {file_id|paper_id, ...} 列表。
            conversation_id: 会话 id（本地副本目录的一部分）。

        Returns:
            list[dict]: [{name, size, path, file_id, paper_id, oss_key}]，本地绝对路径清单。
        """
        out: list[dict] = []
        if not attachments:
            return out
        base = (pathlib.Path(cfg_user_cache_root())
                / _safe_component(x_user_id) / "uploads"
                / _safe_component(conversation_id))
        for att in attachments:
            att = att or {}
            file_id = str(att.get("file_id") or "")
            paper_id = str(att.get("paper_id") or "")
            if paper_id:
                kind, obj_id = "paper", paper_id
            elif file_id:
                kind, obj_id = "file", file_id
            else:
                continue
            try:
                data, meta = _platform_client().attachment(x_user_id, kind, obj_id)
            except Exception as exc:
                logger.warning("附件取回失败（%s=%s）：%s", kind, obj_id, exc)
                continue
            if not data:
                continue
            name = _safe_component(meta.get("name") or obj_id)
            target = base / f"{_safe_component(obj_id)}_{name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.stat().st_size != len(data):
                target.write_bytes(data)
            out.append({"name": name, "size": meta.get("size") or len(data),
                        "path": str(target), "file_id": file_id or None,
                        "paper_id": paper_id or None,
                        "oss_key": meta.get("oss_key") or ""})
        return out

    def _attachment_meta(attachments: list[dict]) -> list[dict]:
        """从解析结果里取「展示用」附件元数据（历史回放复现文件卡片）。

        Args:
            attachments: _resolve_attachments 的返回值。

        Returns:
            list[dict]: [{file_id|paper_id, name, size, oss_key}]，足以渲染卡片并定位原文。
        """
        meta = []
        for att in attachments:
            item = {"name": att.get("name", ""), "size": att.get("size", 0)}
            if att.get("paper_id"):
                item["paper_id"] = att["paper_id"]
            elif att.get("file_id"):
                item["file_id"] = att["file_id"]
            else:
                continue
            if att.get("oss_key"):
                item["oss_key"] = att["oss_key"]
            meta.append(item)
        return meta

    def _persist_user_attachments(user_id: str, conversation_id: str, task: str,
                                  attachments: list[dict]) -> None:
        """把本轮附件元数据回填到用户消息行的 meta（历史回放展示用）。

        用户消息由引擎在 run 内落盘，适配层拿不到它的 id；这里按「会话 + 归属 +
        role=user + 落盘正文的前缀」定位最近一行回填。匹配用注入块前缀而不是全文：
        意图层可能给任务追加澄清附录，正文与送进引擎的文本不必逐字相同。同一会话的
        run 由运行锁串行化，前缀又含本轮附件清单，定位不会串到别的轮次。回填失败
        只丢卡片，不影响本轮回答（错误一律降级为文本）。

        Args:
            user_id: 归属用户。
            conversation_id: 会话 id。
            task: 实际传给引擎的任务文本（含附件清单注入）。
            attachments: 展示用附件元数据。
        """
        if not attachments:
            return
        prefix = task.split("\n\n", 1)[0] + "\n\n"
        try:
            _shared_db().execute(
                "UPDATE bio_message SET meta=? WHERE agent_id=? AND user_id=?"
                " AND role='user' AND LEFT(content, ?)=?"
                " ORDER BY seq DESC LIMIT 1",
                (json.dumps({"attachments": attachments}, ensure_ascii=False),
                 conversation_id, user_id, len(prefix), prefix))
        except Exception:
            logger.warning("附件元数据回填失败（不影响本轮回答）", exc_info=True)

    def _display_task(content: str) -> str:
        """剥掉注入的附件清单块，只留用户原话（历史回放展示用）。

        注入块形如「抬头行 + 若干清单行 + 空行 + 用户原话」。抬头是固定文案，
        据此定位第一个空行，后面就是用户原话。

        Args:
            content: messages.content 原文。

        Returns:
            str: 去掉注入块后的正文；不含注入块时原样返回。
        """
        if not content or not content.startswith(_ATTACHMENT_HEADER):
            return content
        marker = content.find("\n\n")
        return content[marker + 2:] if marker >= 0 else content

    # ---------- 后台循环（定时任务调度已归 Java，这里只保留终端的回收与 KB 对账） ----------

    @app.on_event("startup")
    async def _start_background():
        """应用启动时拉起对账循环与终端回收；随应用关停由事件循环统一回收。

        启动时先补跑一次知识库对账：上一进程崩溃留下的 indexing/queued 行、
        跨栈写入留下的半截状态，都会在这里被拉回一致。所有知识库用户都要审计一次
        ——崩溃可能留下「只剩向量、没有镜像/行」的孤儿，只靠数据库与镜像判据发现不了；
        索引任务幂等，已一致时只做只读对账，不会重复嵌入。
        """
        app.state.shell_reaper = asyncio.create_task(shell_manager.reaper())
        app.state.kb_reconciler = asyncio.create_task(_kb_reconcile_loop())
        try:
            users = set(await asyncio.to_thread(_users_needing_reconcile))
            users |= set(await asyncio.to_thread(_users_with_kb))
            for user_id in sorted(users):
                _schedule_user_index(user_id)
        except Exception:
            logger.warning("启动时知识库状态恢复失败", exc_info=True)

    @app.get("/chat/history")
    async def chat_history(
        conversation_id: str = "",
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        """取一段会话的可见历史（user/assistant 两条腿，按时间正序）。

        会话列表点击回续时前端用它回放消息；tool/system 行不外露——那是
        引擎的内部轨迹，不是对话内容。用户消息带本轮附件时一并返回附件元数据，
        展示正文剥掉注入给模型看的路径清单，只留用户原话。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        if not conversation_id:
            return {"messages": []}
        db = _shared_db()
        rows = db.execute(
            "SELECT role, content, meta, created_at FROM bio_message"
            " WHERE agent_id=? AND user_id=? AND role IN ('user','assistant')"
            " AND content IS NOT NULL AND content != ''"
            " ORDER BY seq", (conversation_id, x_user_id)).fetchall()
        messages = []
        for row in rows:
            item = {
                "role": row["role"],
                "content": _display_task(row["content"]),
                "created_at": row["created_at"],
            }
            if row["role"] == "user" and row["meta"]:
                try:
                    attachments = json.loads(row["meta"]).get("attachments")
                except (ValueError, AttributeError):
                    attachments = None
                if attachments:
                    item["attachments"] = attachments
            messages.append(item)
        return {"messages": messages}

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
        db.execute("DELETE FROM bio_message WHERE agent_id=? AND user_id=?",
                   (conversation_id, x_user_id))
        gone = db.execute("DELETE FROM bio_agent_state WHERE agent_id=? AND user_id=?",
                          (conversation_id, x_user_id))
        agents.pop((x_user_id, conversation_id, user_models.get(x_user_id)), None)
        agent_last_used.pop((x_user_id, conversation_id), None)
        if gone == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"status": "ok"}

    @app.get("/chat/context-usage")
    async def chat_context_usage(
        conversation_id: str = "", x_user_id: str | None = Header(default=None),
    ) -> dict:
        """当前会话的上下文窗口用量分解（head 各块 + 工具 schema + 消息）。

        会话已装配（Agent 在缓存里）时给实时值；未装配（新会话/进程重启/空闲
        驱逐）时退回「固定开销基线 + DB 消息估算」——指示器常显，不因缓存缺席
        而消失。两者都拿不到（该用户从没装配过 Agent）才返回 usage=None。
        """
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        if not conversation_id:
            return {"usage": None}
        agent = agents.get((x_user_id, conversation_id, user_models.get(x_user_id)))
        if agent is not None:
            try:
                return {"usage": agent.context_usage()}
            except Exception:
                logger.warning("上下文用量计算失败", exc_info=True)
        # 未装配路径：基线（head + 工具 schema）+ 消息份（从 DB 逐行估算，
        # 与 estimate_tokens 同口径：正文 + 每条固定协议开销 4）
        baseline = usage_baseline.get((x_user_id, user_models.get(x_user_id)))
        if baseline is None:
            return {"usage": None}
        parts = dict(baseline["parts"])
        try:
            from biopilot.common.core.utils.tokenization import (
                estimate_text_tokens)
            rows = _shared_db().execute(
                "SELECT role, content, tool_calls FROM bio_message"
                " WHERE agent_id=? AND user_id=?",
                (conversation_id, x_user_id)).fetchall()
            msg_tokens = 0
            for r in rows:
                text = f"{r['role']}: {r['content'] or ''}"
                if r["tool_calls"]:
                    text += r["tool_calls"]
                msg_tokens += estimate_text_tokens(text) + 4
            parts["messages"] = msg_tokens
        except Exception:
            parts["messages"] = 0
        return {"usage": {"total": sum(parts.values()),
                          "limit": baseline["limit"], "parts": parts}}

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

        # 附件：落本地副本 + 生成清单（元数据行注入任务文本；沙箱挂目录读数据）
        attachments = _resolve_attachments(
            x_user_id, (body or {}).get("attachments") or [], conversation_id)
        attachment_meta = _attachment_meta(attachments)
        # 用户原话先留一份：标题与历史展示都只取原话，不取后面注入的路径清单
        user_task = task
        if attachments:
            lines = [f"{_ATTACHMENT_HEADER}（沙箱内见 /corpus/uploads/，本机见列出的路径）："]
            for a in attachments:
                lines.append(f"- {a['name']}（{a['size']} 字节）路径：{a['path']}")
            task = "\n".join(lines) + "\n\n" + task

        key = (x_user_id, conversation_id, user_models.get(x_user_id))
        if key not in agents:
            built = agent_factory(x_user_id, conversation_id,
                                  _confirm_callback(x_user_id, conversation_id),
                                  project_id)
            # 工厂可为同步或异步（真实装配是 async，测试替身是同步 lambda）
            agents[key] = await built if asyncio.iscoroutine(built) else built
            # 装配即快照固定开销基线（head 各块 + 工具 schema）：装配后窗口为空，
            # 消息份为 0，正好是要缓存的份额；失败只少一份基线，不阻塞对话
            try:
                snap = agents[key].context_usage()
                usage_baseline[(x_user_id, user_models.get(x_user_id))] = {
                    "parts": {k: v for k, v in snap["parts"].items()
                              if k != "messages"},
                    "limit": snap["limit"],
                }
            except Exception:
                logger.debug("上下文用量基线快照失败", exc_info=True)
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
                    "type": str(getattr(event, "kind", "content")).replace("AgentEventKind.", "").lower(),
                    "text": getattr(event, "text", "") or "",
                    "agent_type": getattr(event, "agent_type", ""),
                    "tool_name": getattr(event, "tool_name", "") or "",
                    "completion": getattr(event, "completion", "") or "",
                    "duration_ms": getattr(event, "duration_ms", None),
                })

            async def run_task() -> str:
                # 标题在 run 开始时就落库：用户中断长任务后会话也不该只剩一个 UUID 片段；
                # 它只读一次 name，不会覆盖之后的手工改名。用用户原话，不用注入清单。
                await _autotitle(x_user_id, conversation_id, user_task)
                try:
                    # 全局并发闸（run 粒度）：多用户在途 run 总上限，批量派发占不满外部资源
                    async with llm_gate:
                        answer = await agent.run(task, stream_callback=on_event)
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
                finally:
                    # 用户消息此时已随 run 落盘：回填附件元数据，历史回放才能复现文件卡片
                    _persist_user_attachments(x_user_id, conversation_id, task,
                                              attachment_meta)

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
            if cfg.runtime.find_model_entry(name) is None:
                raise HTTPException(status_code=422, detail=f"未知模型：{name}")
            user_models[x_user_id] = name
        else:
            user_models[x_user_id] = None    # 回到主模型
        return {"status": "ok", "selected": user_models.get(x_user_id)}

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

    # 删户两阶段：标记 → 等活动清零 → 物理删除（幂等）。只清引擎数据；
    # 平台表行与 OSS 对象由 Java 在同一个删户流程里清理。
    @app.post("/internal/users/{target_id}/mark-deleting")
    async def mark_deleting(
        target_id: str,
        x_user_id: str | None = Header(default=None),
        x_internal_token: str | None = Header(default=None),
    ) -> dict:
        _internal_user(x_user_id, x_internal_token)
        db = _shared_db()
        db.execute("UPDATE bio_agent_state SET user_id=CONCAT('deleting:', user_id)"
                   " WHERE user_id=? AND user_id NOT LIKE 'deleting:%'", (target_id,))
        return {"status": "marked"}

    @app.post("/internal/users/{target_id}/purge")
    async def purge_user(
        target_id: str,
        x_user_id: str | None = Header(default=None),
        x_internal_token: str | None = Header(default=None),
    ) -> dict:
        """物理清除该用户的全部引擎数据（幂等，可重复执行）。

        agent_state 在 mark-deleting 阶段被改名为 `deleting:<uid>`，这里两种
        形态都清；其余引擎表从未改名，按原 uid 删。平台表（论文/文档/引用/项目/
        定时任务）与 OSS 对象归 Java，不在这里删。
        """
        _internal_user(x_user_id, x_internal_token)
        db = _shared_db()
        for table in ("bio_message", "bio_memory_block", "bio_memory_block_history"):
            try:
                db.execute(f"DELETE FROM {table} WHERE user_id=?", (target_id,))
            except Exception:
                logger.warning("删户清理跳过 %s（表不存在或不可达）", table)
        db.execute("DELETE FROM bio_agent_state WHERE user_id=?"
                   " OR user_id LIKE CONCAT('deleting:', ?)", (target_id, target_id))
        return {"status": "purged", "user_id": target_id}

    # 终端：按用户持久化的宿主 shell（面板关闭/切换会话不杀进程）。
    # 是否允许启动宿主 shell 由 runtime.allow_host_shell 显式控制；缺 X-User-Id
    # 一律拒连（与 HTTP 端点同一信任边界）。
    @app.get("/terminal/config")
    async def terminal_config(x_user_id: str | None = Header(default=None)) -> dict:
        """返回当前部署是否启用宿主终端（前端据此决定按钮是否可用）。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        shell = os_env("SHELL", "/bin/sh") or "/bin/sh"
        return {
            "enabled": bool(cfg.runtime.allow_host_shell),
            "shell": pathlib.Path(shell).name,
        }

    @app.post("/terminal/restart")
    async def terminal_restart(x_user_id: str | None = Header(default=None)) -> dict:
        """结束该用户当前的 shell；下一次打开面板会启动新进程。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        from biopilot.config import BioPilotConfig
        if not BioPilotConfig.from_env().runtime.allow_host_shell:
            raise HTTPException(status_code=403, detail="当前部署未启用宿主终端")
        restarted = await shell_manager.restart(x_user_id)
        return {"status": "restarted" if restarted else "no-session"}

    @app.websocket("/ws/terminal")
    async def ws_terminal(ws: WebSocket):
        """终端 WebSocket：附着到该用户的持久 shell，断线只脱离不杀进程。

        客户端 → 服务端使用 JSON 文本帧（input/resize），服务端 → 客户端是
        原始终端输出文本；重连时先回放缓冲，用户能看到上次的屏幕内容。
        """
        x_user_id = ws.headers.get("x-user-id", "")
        if not x_user_id:
            await ws.close(code=1008, reason="缺少 X-User-Id 请求头")
            return
        from biopilot.config import BioPilotConfig
        if not BioPilotConfig.from_env().runtime.allow_host_shell:
            await ws.close(code=1008, reason="当前部署未启用宿主终端")
            return
        await ws.accept()
        try:
            session = await shell_manager.attach(x_user_id, ws)
        except Exception:
            await ws.close(code=1011, reason="终端启动失败")
            return
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    payload = None
                if isinstance(payload, dict) and payload.get("type") == "input":
                    await session.write(str(payload.get("data") or ""))
                elif isinstance(payload, dict) and payload.get("type") == "resize":
                    try:
                        session.resize(int(payload.get("cols") or 0),
                                       int(payload.get("rows") or 0))
                    except (TypeError, ValueError):
                        pass
                elif payload is None:
                    # 兼容旧客户端：纯文本即键盘输入
                    await session.write(raw)
        except Exception:
            # 客户端关闭/网络断开：只脱离，保留 shell 供下次继续
            pass
        finally:
            shell_manager.detach(session, ws)


    # ---------- 内部接口（只给 Java 平台调） ----------

    def _internal_user(x_user_id: str | None, x_internal_token: str | None) -> str:
        """校验内部调用头：token（配置了才校验）+ 归属用户。"""
        expected = os_env("BIOPILOT_INTERNAL_TOKEN", "") or ""
        if expected and x_internal_token != expected:
            raise HTTPException(status_code=403, detail="内部调用 token 无效")
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        return x_user_id

    @app.post("/internal/kb/sync")
    async def internal_kb_sync(
        body: dict | None = None,
        x_user_id: str | None = Header(default=None),
        x_internal_token: str | None = Header(default=None),
    ) -> dict:
        uid = _internal_user(x_user_id, x_internal_token)
        _schedule_user_index(uid)
        return {"status": "ok"}

    @app.get("/internal/kb/runtime")
    async def internal_kb_runtime(
        x_user_id: str | None = Header(default=None),
        x_internal_token: str | None = Header(default=None),
    ) -> dict:
        """知识库运行时信息，供 Java 概览合并（纯内存/配置读取，不碰 RAG 锁）。

        计数与论文清单归 Java 查 `bio_paper`；这里只补 Java 拿不到的引擎侧状态：
        用户域 collection 名、嵌入模型、索引任务是否在跑、最近一轮结果。

        Args:
            x_user_id: 归属用户（即 RAG 用户域）。
            x_internal_token: 内部调用共享 token。

        Returns:
            dict: ``{collection, embedding_model, running, last_run}``。
        """
        from biopilot.config import BioPilotConfig

        uid = _internal_user(x_user_id, x_internal_token)
        cfg = BioPilotConfig.from_env()
        collection = cfg.rag.storage.collection + (
            "" if uid == "local" else f"_{uid}")
        return {
            "collection": collection,
            "embedding_model": cfg.rag.embedding.embed_model,
            "running": uid in reindex_running,
            "last_run": kb_last_run.get(uid),
        }

    @app.post("/internal/schedule/run")
    async def internal_schedule_run(
        body: dict,
        x_user_id: str | None = Header(default=None),
        x_internal_token: str | None = Header(default=None),
    ) -> dict:
        """Java 调度器投递到期任务：立即返回，后台跑一轮 agent。

        时间推进由 Java 在认领时完成（投递失败也推进，防每轮重试刷爆），这里只
        负责执行与进程内去重；与网页对话共用同一个全局并发闸。

        Args:
            body: ``{task_id, conversation_id, task, name}``。
            x_user_id: 归属用户。
            x_internal_token: 内部调用共享 token。

        Returns:
            ``{status: accepted|skipped}``。
        """
        uid = _internal_user(x_user_id, x_internal_token)
        payload = body or {}
        conversation_id = str(payload.get("conversation_id") or "")
        task = str(payload.get("task") or "")
        task_id = str(payload.get("task_id") or "")
        if not conversation_id or not task:
            raise HTTPException(status_code=422,
                                detail="conversation_id 与 task 必填")
        key = task_id or f"{uid}:{conversation_id}:{task[:32]}"
        if key in _sched_running:
            return {"status": "skipped"}
        _sched_running.add(key)
        asyncio.get_running_loop().create_task(_execute_scheduled(
            uid, conversation_id, "【定时任务】" + task, key, agent_factory, llm_gate))
        return {"status": "accepted"}

    _kb_endpoints(app)
    return app


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


#: 正在执行的定时任务 id（进程内去重；跨实例由 Java 的 CAS 认领负责）
_sched_running: set = set()


async def _execute_scheduled(user_id: str, conversation_id: str, task: str,
                             key: str, agent_factory, gate) -> None:
    """执行一次定时任务：与网页对话同一装配路径、同一全局并发闸。

    参数显式传入（工厂与闸由适配层注入），测试可直接 await 它而不依赖后台任务。

    Args:
        user_id: 归属用户。
        conversation_id: 归属会话。
        task: 任务文本（调用方已加「【定时任务】」前缀）。
        key: 进程内去重键（task_id）。
        agent_factory: 会话工厂（与对话同一路径）。
        gate: asyncio.Semaphore，全局并发闸。
    """
    try:
        async with gate:
            built = agent_factory(user_id, conversation_id)
            agent = await built if asyncio.iscoroutine(built) else built
            await agent.run(task)
    except Exception:
        logger.warning("定时任务执行失败（%s）", key, exc_info=True)
    finally:
        _sched_running.discard(key)


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


#: 每用户索引 singleflight（模块级：加入知识库与手动重建共用，防并发重复跑）
reindex_running: set[str] = set()
#: 跑到一半又来了新请求：当前轮结束后再补跑一次（否则新加入的论文会一直排队）
reindex_pending: set[str] = set()
#: 最近一次索引结果（内存态，供知识库页展示；重启后清空）
kb_last_run: dict[str, dict] = {}


#: 单次索引最多重扫几遍：索引期间新加入的论文会在下一遍接着处理
_KB_INDEX_PASSES = 3
#: 索引锁被另一个进程占用时的补跑次数（每次间隔 2 秒）；超时交给周期对账
_KB_LOCK_RETRIES = 15
#: 周期对账间隔（秒）：兜住跨进程丢唤醒、崩溃遗留与半截状态
_KB_SWEEP_SECONDS = 300


def _drop_paper_index(svc, target: pathlib.Path) -> None:
    """撤销一篇论文的索引与镜像（并发移出后的补偿；失败只留日志）。

    Args:
        svc: RAGService，当前用户域实例。
        target: 镜像 PDF 路径。
    """
    try:
        svc.remove_document(str(target))
    except Exception:
        logger.warning("撤回已移出论文的索引失败（%s）", target, exc_info=True)
    try:
        target.unlink(missing_ok=True)
    except Exception:
        logger.warning("撤回已移出论文的镜像失败（%s）", target, exc_info=True)


def _index_user_kb_sync(user_id: str) -> dict:
    """把该用户「已加入知识库」的论文逐篇索引，并清理已移出的论文。

    逐篇索引用 ``index_document``：它内部先删后建，能给出单篇的分块数与失败原因。
    已移出的论文走 ``remove_document`` 只删索引，不动 papers 行和 OSS 原文。

    并发防护（跨栈写入的收敛点）：
      - 同一用户同一时刻只允许一个索引者，用 MySQL 命名锁 ``kb-index:<uid>``
        跨进程互斥；锁随连接自动释放，进程崩溃不会留下死锁；
      - 拿到锁后先让 Java `/internal/kb/normalize` 收敛半截与僵尸状态；
      - 结果上报由 Java 按 `kb_enabled` 与 `indexing` 前置条件落盘，索引期间被
        移出的论文会返回 applied=false，引擎据此撤回刚建好的索引；
      - 索引期间新加入的论文在下一遍重扫里接着处理。

    Args:
        user_id: 归属用户（即 RAG 用户域）。

    Returns:
        dict: indexed/failed/removed/orphans/drifted 计数与 finished_at；
        skipped=True 表示锁被另一个进程持有，本轮没有做任何事。
    """
    from datetime import datetime, timezone
    from biopilot.config import BioPilotConfig
    from biopilot.core.memory.storage.named_lock import NamedLock

    cfg = BioPilotConfig.from_env()
    lock = NamedLock(cfg.runtime.memory_dsn)
    lock_name = f"kb-index:{user_id}"
    acquired = False
    lock_usable = True
    try:
        acquired = lock.acquire(lock_name, timeout=15)
    except Exception:
        # 锁服务异常不阻断索引（bio_paper 同库，真不可达时索引本身也会失败）；
        # 降级为无锁执行，状态更新仍有条件守卫，不会写出互斥以外的错值。
        lock_usable = False
        logger.warning("知识库索引锁不可用，本轮无锁执行（%s）", user_id, exc_info=True)
    if lock_usable and not acquired:
        return {"indexed": 0, "failed": 0, "removed": 0, "orphans": 0,
                "drifted": 0, "skipped": True,
                "finished_at": datetime.now(timezone.utc).isoformat()}
    try:
        return _index_user_kb_locked(user_id, cfg)
    finally:
        if acquired:
            lock.release(lock_name)


def _index_user_kb_locked(user_id: str, cfg) -> dict:
    """持有该用户索引锁后执行一轮完整索引（对账 → 逐篇索引 → 清理）。

    状态写者只有 Java：本函数通过 ``/internal/kb/normalize``、``/indexing``、
    ``/requeue-all``、``/result`` 驱动状态迁移；Java 返回的 ``applied`` 决定是否
    撤回刚建好的向量与镜像。

    一致性对账以 MySQL 的 ``bio_paper`` 为唯一真相：
      - 向量库里有、但对应论文不在知识库的块 → 删除（覆盖「镜像已丢、只剩向量」）；
      - 已就绪论文的向量块数与 ``chunk_count`` 不一致（缺失/偏多/偏少）→ 强制重建；
      - ``failed`` 不参与自动重试（用户点重试时 Java 先置 ``queued``），避免对账反复
        消耗解析与嵌入资源。

    Args:
        user_id: 归属用户。
        cfg: BioPilotConfig，配置快照。

    Returns:
        dict: indexed/failed/removed/orphans/drifted 计数与 finished_at。
    """
    from datetime import datetime, timezone
    from biopilot.core.rag.constants import IndexOutcomeStatus
    from biopilot.core.rag.services.rag_service import get_rag_service

    svc = get_rag_service(cfg, user_domain=user_id)
    db = _shared_db()
    platform = _platform_client()
    mirror = pathlib.Path(svc.config.corpus.pdf_dir)
    mirror.mkdir(parents=True, exist_ok=True)
    mirror_root = mirror.resolve()

    # ---- 向量库 ↔ 平台表对账（MySQL 是唯一真相） ----
    # 只在能读到向量库时做：读失败不等于库是空的，不能把所有「已就绪」论文误判成漂移。
    indexed = failed = removed = orphans = 0
    drift: set[str] = set()
    try:
        vector_counts: dict[str, int] | None = svc.document_chunk_counts()
    except Exception:
        vector_counts = None
        logger.warning("向量库对账读取失败，本轮跳过漂移检测（%s）", user_id,
                       exc_info=True)
    if vector_counts is not None:
        rows = db.execute(
            "SELECT id, kb_enabled, index_status, chunk_count FROM bio_paper"
            " WHERE user_id=?", (user_id,)).fetchall()
        enabled_ids = {row["id"] for row in rows if row["kb_enabled"]}
        # 1) 向量库里不属于任何「已加入」论文的块：删掉。镜像文件由后面的清理统一删，
        #    这里覆盖「镜像已经不在、只剩向量」的孤儿——只靠文件扫描发现不了。
        for path in list(vector_counts):
            try:
                resolved = pathlib.Path(path).resolve()
                resolved.relative_to(mirror_root)
            except (OSError, ValueError):
                # 不是本用户镜像目录下的路径：不认识的域，宁可不删
                continue
            if resolved.stem in enabled_ids:
                continue
            try:
                if svc.remove_document(path):
                    orphans += 1
                    logger.warning("清理孤儿向量：%s（%s）", path, user_id)
                vector_counts.pop(path, None)
            except Exception:
                logger.warning("清理孤儿向量失败（%s）", path, exc_info=True)
        # 2) 已就绪论文的向量块数必须与平台 chunk_count 一致；缺失、偏多、偏少都重建
        for row in rows:
            if not row["kb_enabled"] or row["index_status"] != "indexed":
                continue
            paper_id = str(row["id"])
            expected = int(row.get("chunk_count") or 0)
            actual = vector_counts.get(
                str((mirror / f"{paper_id}.pdf").resolve()), 0)
            if actual == 0 or actual != expected:
                drift.add(paper_id)
                logger.warning(
                    "论文索引与平台状态不一致，将重建：%s（数据库 %d 块，向量库 %d 块）",
                    paper_id, expected, actual)

    seen: set[str] = set()
    for _pass in range(_KB_INDEX_PASSES):
        # 每遍先让 Java 收敛：半截状态与崩溃遗留的 indexing 都拉回可执行状态。
        # 持锁时才敢把 indexing 判为僵尸；平台不可达则本轮直接退出，下一轮重试。
        try:
            platform.kb_normalize(user_id, requeue_indexing=True)
        except Exception:
            logger.warning("知识库状态收敛失败（%s），本轮跳过", user_id, exc_info=True)
            break
        rows = db.execute(
            "SELECT id, oss_key, kb_enabled, index_status, title FROM bio_paper"
            " WHERE user_id=?",
            (user_id,)).fetchall()
        enabled = {row["id"]: row for row in rows if row["kb_enabled"]}
        todo = []
        for paper_id, row in enabled.items():
            if paper_id in seen:
                continue
            target = mirror / f"{paper_id}.pdf"
            # 失败等用户显式重试（Java 会先置 queued）；周期/启动对账不能反复烧嵌入
            if row["index_status"] == "failed":
                continue
            if (row["index_status"] == "indexed" and target.exists()
                    and paper_id not in drift):
                continue
            todo.append((paper_id, row, target))
        if not todo:
            break
        try:
            accepted = set(platform.kb_indexing(
                user_id, [paper_id for paper_id, _row, _target in todo]))
        except Exception:
            logger.warning("索引状态置位失败（%s），本轮跳过", user_id, exc_info=True)
            break
        if not accepted:
            break
        seen.update(accepted)

        results: list[dict] = []
        for paper_id, row, target in todo:
            if paper_id not in accepted:
                continue
            try:
                if not target.exists():
                    data, _meta = platform.attachment(user_id, "paper", paper_id)
                    if not data:
                        raise RuntimeError("论文原文取回失败")
                    target.write_bytes(data)
                # 标题只从数据库取（Java 提取并落库），索引不再自己解析标题
                outcome = svc.index_document(str(target), title=row.get("title") or None)
                status = getattr(outcome, "status", None)
                if status == IndexOutcomeStatus.INDEXED:
                    results.append({"paper_id": paper_id, "ok": True,
                                    "chunks": int(getattr(outcome, "chunks", 0) or 0),
                                    "error": ""})
                else:
                    reason = getattr(outcome, "reason", "") or f"未入库（{status}）"
                    results.append({"paper_id": paper_id, "ok": False,
                                    "chunks": 0, "error": reason})
            except Exception as exc:
                logger.warning("论文索引失败（%s）", paper_id, exc_info=True)
                results.append({"paper_id": paper_id, "ok": False,
                                "chunks": 0, "error": str(exc)})

        reported = False
        applied: dict = {}
        if results:
            try:
                applied = platform.kb_result(user_id, results)
                reported = True
            except Exception:
                # 状态未知：保留已建好的索引，下一轮按 indexing 重排后幂等重建
                logger.warning("索引结果上报失败（%s）", user_id, exc_info=True)

        for item in results:
            paper_id = str(item["paper_id"])
            if not item["ok"]:
                failed += 1
                continue
            if not reported:
                continue
            if applied.get(paper_id):
                indexed += 1
            else:
                # 索引期间被移出：撤回刚建好的向量与镜像，两边都不留残留
                _drop_paper_index(svc, mirror / f"{paper_id}.pdf")

    # 已移出知识库（或已删除）的论文：删镜像与索引块；文件本身在 OSS 里不动
    rows = db.execute(
        "SELECT id, kb_enabled FROM bio_paper WHERE user_id=?", (user_id,)).fetchall()
    enabled = {row["id"] for row in rows if row["kb_enabled"]}
    for path in mirror.glob("*.pdf"):
        if path.stem in enabled:
            continue
        try:
            svc.remove_document(str(path))
            path.unlink(missing_ok=True)
            removed += 1
        except Exception:
            logger.warning("清理已移出论文的索引失败（%s）", path, exc_info=True)

    # 收尾再收敛一次（不重排本轮刚置 indexing 的行）：不留「已就绪但不在知识库」
    try:
        platform.kb_normalize(user_id, requeue_indexing=False)
    except Exception:
        logger.warning("知识库收尾收敛失败（%s）", user_id, exc_info=True)

    summary = {
        "indexed": indexed,
        "failed": failed,
        "removed": removed,
        "orphans": orphans,
        "drifted": len(drift),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    kb_last_run[user_id] = summary
    return summary


def _users_with_kb() -> list[str]:
    """列出知识库里还有勾选论文的用户（启动对账用）。

    启动时给每个用户域做一次向量库审计，覆盖「崩溃后只剩向量、数据库行和镜像
    都已不在」的孤儿——这类残留用数据库与镜像判据都发现不了。

    Returns:
        list[str]: 用户 id（去重排序）。
    """
    rows = _shared_db().execute(
        "SELECT DISTINCT user_id FROM bio_paper WHERE kb_enabled=1").fetchall()
    return sorted({str(row["user_id"]) for row in rows if row.get("user_id")})


def _users_needing_reconcile() -> list[str]:
    """列出知识库派生状态不自洽的用户（启动恢复与周期对账共用）。

    判据两类：

    - 行内不自洽：勾选了但还没进入可检索状态，或者没勾选却留着索引痕迹。
      失败（failed）不算——它等用户点重试，周期对账不自动重跑，避免反复
      消耗解析与嵌入资源。
    - 行外不自洽：镜像目录里还有 PDF，但对应行已经删除、或已不在知识库。
      论文删除后的索引清理是异步通知，通知丢失时向量会留在检索面里；按
      镜像目录反查能把这些孤儿收回来。

    Returns:
        list[str]: 需要跑一轮索引/清理的用户 id。
    """
    db = _shared_db()
    rows = db.execute(
        "SELECT user_id, id, kb_enabled, indexed, index_status, index_error,"
        " indexed_at, chunk_count FROM bio_paper"
    ).fetchall()
    stale = {
        row["user_id"] for row in rows
        if row.get("user_id") and (
            (int(row.get("kb_enabled") or 0) == 1
             and str(row.get("index_status") or "") in ("not_added", "queued", "indexing"))
            or (int(row.get("kb_enabled") or 0) == 0 and (
                int(row.get("indexed") or 0) != 0
                or str(row.get("index_status") or "not_added") != "not_added"
                or int(row.get("chunk_count") or 0) != 0
                or row.get("index_error") is not None
                or row.get("indexed_at") is not None))
        )
    }
    return sorted(stale | _users_with_orphan_mirrors(rows))


def _users_with_orphan_mirrors(rows: list[dict],
                               workspace: str | None = None) -> set[str]:
    """按镜像目录反查「有 PDF 但对应行已删除/未加入」的用户。

    Args:
        rows: 全量 bio_paper 行（含 user_id/id/kb_enabled，避免二次查询）。
        workspace: 工作区根（测试注入口）；缺省取当前配置。

    Returns:
        set[str]: 存在孤儿镜像的用户 id。
    """
    import re as _re

    from biopilot.config import BioPilotConfig

    root = (pathlib.Path(workspace) if workspace
            else pathlib.Path(BioPilotConfig.from_env().runtime.workspace))
    enabled: dict[str, set[str]] = {}
    safe_to_user: dict[str, str] = {}
    for row in rows:
        user_id = str(row.get("user_id") or "")
        if not user_id:
            continue
        safe_to_user[_re.sub(r"[^A-Za-z0-9_-]", "_", user_id)] = user_id
        if int(row.get("kb_enabled") or 0):
            enabled.setdefault(user_id, set()).add(str(row["id"]))
    base = root / "rag" / "users"
    if not base.is_dir():
        return set()
    stale: set[str] = set()
    for directory in base.iterdir():
        user_id = safe_to_user.get(directory.name)
        if user_id is None or not directory.is_dir():
            continue
        papers = directory / "papers"
        if not papers.is_dir():
            continue
        keep = enabled.get(user_id, set())
        if any(path.stem not in keep for path in papers.glob("*.pdf")):
            stale.add(user_id)
    return stale


async def _kb_reconcile_loop() -> None:
    """周期对账循环：把跨进程丢失的唤醒、崩溃遗留、半截状态拉回一致。"""
    while True:
        await asyncio.sleep(_KB_SWEEP_SECONDS)
        try:
            for user_id in await asyncio.to_thread(_users_needing_reconcile):
                _schedule_user_index(user_id)
        except Exception:
            logger.warning("知识库周期对账异常", exc_info=True)


def _schedule_user_index(user_id: str) -> None:
    """在事件循环里后台触发一次该用户的知识库索引（singleflight + 补跑）。

    旧实现在重建期间直接丢弃新请求；用户连续勾选两批论文时第二批会永远停在
    queued。这里用 pending 标记在当前轮结束后补跑；跨进程的互斥由索引锁
    承担，锁被另一进程持有时本轮稍后重试，避免「B 进程的请求被 A 进程吃掉
    后再也没人触发」。

    Args:
        user_id: 归属用户（即 RAG 用户域）。
    """
    if user_id in reindex_running:
        reindex_pending.add(user_id)
        return
    reindex_running.add(user_id)

    async def _runner():
        try:
            misses = 0
            while True:
                reindex_pending.discard(user_id)
                summary = await asyncio.to_thread(_index_user_kb_sync, user_id)
                if summary.get("skipped"):
                    misses += 1
                    if misses > _KB_LOCK_RETRIES:
                        logger.info("知识库索引锁持续被占用，交给周期对账（%s）", user_id)
                        break
                    await asyncio.sleep(2)
                    reindex_pending.add(user_id)
                else:
                    misses = 0
                if user_id not in reindex_pending:
                    break
        except Exception:
            logger.warning("知识库索引失败（%s）", user_id, exc_info=True)
        finally:
            reindex_running.discard(user_id)

    asyncio.get_running_loop().create_task(_runner())


def cfg_runtime_workspace() -> str:
    """当前工作区根（配置派生；本地路径拼装共用）。"""
    from biopilot.config import BioPilotConfig
    return BioPilotConfig.from_env().runtime.workspace


def cfg_user_cache_root() -> str:
    """按用户隔离的派生缓存根（附件副本与技能物化的落点）。"""
    from biopilot.config import BioPilotConfig, user_cache_root
    return str(user_cache_root(BioPilotConfig.from_env()))



#: 知识库只读端点等待 RAG 锁的上限（秒）。索引持锁期间会跑嵌入与看图，
#: 可能持续数分钟；只读请求不能排在事件循环里等它，宁可快速失败让前端提示。
_KB_LOCK_WAIT_SECONDS = 5.0


class _KbBusyError(RuntimeError):
    """知识库正被索引占用，只读请求快速失败而不是排队阻塞。"""


def _kb_read_locked(svc, fn, *args, **kwargs):
    """在 worker 线程里持 RAG 锁执行只读操作，锁被索引占用超限即报错。

    ``fn`` 通常是 RAGService 的只读方法（内部还会再取同一把可重入锁）。
    调用方必须用 ``asyncio.to_thread`` 执行本函数：直接在事件循环线程里阻塞取锁
    会把整个适配层卡死——状态、论文清单等无关请求会一起悬挂，前端表现为整页空数据。

    Args:
        svc: RAGService（或测试替身），需提供可重入的 ``lock``。
        fn: 只读操作。
        *args: 传给 ``fn`` 的位置参数。
        **kwargs: 传给 ``fn`` 的关键字参数。

    Returns:
        ``fn`` 的返回值。

    Raises:
        _KbBusyError: 超过 ``_KB_LOCK_WAIT_SECONDS`` 仍未拿到锁。
    """
    if not svc.lock.acquire(timeout=_KB_LOCK_WAIT_SECONDS):
        raise _KbBusyError("知识库正在索引，请稍后再试")
    try:
        return fn(*args, **kwargs)
    finally:
        svc.lock.release()


def _kb_endpoints(app: FastAPI) -> None:
    """知识库 RAG 端点：索引触发、试检索、分块列表。

    平台侧的状态概览与论文清单归 Java（`bio_paper` 是唯一真相）；这里只暴露
    需要读向量库的能力，不再查平台表。
    """
    import time as _time

    from biopilot.config import BioPilotConfig
    from biopilot.core.rag.services.rag_service import get_rag_service

    def _chunk_view(chunk, score=None) -> dict:
        """把 Chunk 转成前端可渲染的字典（正文截断，避免一次返回整篇）。"""
        return {
            "id": chunk.id,
            "text": (chunk.text or "")[:800],
            "path": chunk.path,
            "title": chunk.title,
            "heading": chunk.heading,
            "caption": chunk.caption,
            "chunk_type": chunk.chunk_type,
            "chunk_index": chunk.chunk_index,
            "page": list(chunk.page_num) if chunk.page_num else [],
            "has_image": bool(chunk.image_key),
            "score": score,
        }

    @app.post("/kb/reindex")
    async def kb_reindex(
        body: dict | None = None,
        force: bool = False,
        x_user_id: str | None = Header(default=None),
    ) -> dict:
        """重建知识库：默认只补排队/失败/缺文件的论文；force=true 时全部重扫。"""
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        if force:
            # `bio_paper` 只有 Java 能写；引擎只发触发请求，不直接 UPDATE
            from biopilot.common.platform import PlatformError

            try:
                await asyncio.to_thread(
                    _platform_client().kb_requeue_all, x_user_id)
            except PlatformError as exc:
                raise HTTPException(
                    status_code=503, detail="索引状态重置失败：平台不可达") from exc
        _schedule_user_index(x_user_id)
        return {"status": "started", "already_running": x_user_id in reindex_running}

    @app.post("/kb/search")
    async def kb_search(body: dict, x_user_id: str | None = Header(default=None)) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        query = ((body or {}).get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=422, detail="query 不能为空")
        try:
            top_k = int((body or {}).get("top_k") or 8)
        except (TypeError, ValueError):
            top_k = 8
        top_k = max(1, min(top_k, 30))
        cfg = BioPilotConfig.from_env()
        svc = get_rag_service(cfg, user_domain=x_user_id)
        started = _time.monotonic()
        try:
            # 检索含嵌入与精排的网络调用，必须挪出事件循环；索引持锁时快速失败，
            # 否则整页请求会一起排队悬挂。
            hits = await asyncio.to_thread(
                _kb_read_locked, svc, svc.retrieve_scored, query, top_k)
        except _KbBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        elapsed = int((_time.monotonic() - started) * 1000)
        results = []
        for chunk, score in hits:
            item = _chunk_view(chunk, score=round(float(score or 0), 4))
            # 只回 paper_id；文件展示字段由 Java 的论文清单在前端 join
            item["paper_id"] = Path(chunk.path).stem
            results.append(item)
        return {"results": results, "elapsed_ms": elapsed, "query": query}

    @app.get("/kb/papers/{paper_id}/chunks")
    async def kb_paper_chunks(
        paper_id: str, x_user_id: str | None = Header(default=None),
    ) -> dict:
        if not x_user_id:
            raise HTTPException(status_code=403, detail="缺少 X-User-Id 请求头")
        cfg = BioPilotConfig.from_env()
        svc = get_rag_service(cfg, user_domain=x_user_id)
        path = str(Path(svc.config.corpus.pdf_dir) / f"{paper_id}.pdf")
        try:
            # 分块读取要遍历整库向量，索引写库期间必须让出事件循环，
            # 锁被占用超限就明确告知「正在索引」，不让页面无限转圈。
            chunks = await asyncio.to_thread(
                _kb_read_locked, svc, svc.list_document_chunks, path)
        except _KbBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        chunks.sort(key=lambda chunk: chunk.chunk_index)
        return {"chunks": [_chunk_view(chunk) for chunk in chunks]}
