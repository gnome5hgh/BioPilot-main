"""工具调用执行管道：中间件洋葱 + 参数解析 + 三把锁 + 结构化事件收口。

从 Agent 上整块搬出来的——它此前与 Agent 实例强耦合（读 7 个 self 属性），
现在是一个独立的协作对象。**只有构造后不会被替换的东西才按值注入**：

- 构造期：中间件链、agent_type / session_id / instance_id / has_human_confirm；
- 调用期传入：`tools`、`confirm_callback`、`stream_sink` —— 这三样在真实流程里会被构造后
  替换（spawn 用 `_wrap_confirm_callback` 把用户确认等待排除出超时预算；Web 适配层在
  装配好之后才把流式回调挂到 supervisor；测试直接整表换 `tools`）。按值
  捕获会拿到过期引用，所以每次调用由调用方现取现传。

管道主体是「查工具 → 解析参数 → 引用形状校验 → before 钩子 → 执行 → 逆序 after 钩子
→ 一条 tool_end 收口」，也是「所有错误降级为文本」这条策略的唯一落点：任何异常都
变成 ToolResult 文本回给模型（只有 MaxTurnsExceeded 向上抛，那在 Agent.run 里）。
"""

import asyncio
import json
import sys
import time
from datetime import datetime

from biopilot.core.agent.constants import AgentEventKind
from biopilot.core.agent.domain import AgentEvent
from biopilot.core.agent.services.state import get_run_state
from biopilot.core.security import (
    ApprovalOutcome, ConfirmRequired, SecurityError, ToolContext,
)
from biopilot.core.tool import (
    SUMMARY_DECISION, SUMMARY_VIOLATIONS, ToolResult,
)
from biopilot.core.tool.services.validation import validate_ref_args

__all__ = ["ToolExecutor"]



class ToolExecutor:
    """单个工具调用的执行管道（无状态；可变依赖由调用方每次传入）。

    Attributes:
        _middleware: list[SecurityMiddleware]，before 顺序 / after 逆序
        _agent_type / _session_id / _user_id: str，写进 ToolContext 供审计聚合
        _instance_id: str，本实例标识（同路径写占用的持有者判定）
        _has_human_confirm: bool，是否有真实人工确认回调（区分 user_denied /
            auto_denied）——按构造标志而非回调身份判断，因为 spawn 会包装回调
    """

    def __init__(self, *, middleware, agent_type: str, session_id: str,
                 instance_id: str, has_human_confirm: bool,
                 offloader=None, user_id: str | None = None):
        """
        Args:
            middleware: list，安全中间件链
            agent_type: str，Agent 类型标识
            session_id: str，会话标识
            instance_id: str，实例唯一标识（写占用按它认持有者）
            has_human_confirm: bool，构造时是否有真实人工确认回调
            offloader: callable | None，大工具结果外置回调；None 时跳过
        """
        self._middleware = middleware
        self._agent_type = agent_type
        self._session_id = session_id
        self._user_id = user_id
        self._instance_id = instance_id
        self._has_human_confirm = has_human_confirm
        self._offloader = offloader

    async def execute(self, tool_call: dict, *, trace_id: str | None,
                      turn: int = 0, confirm_lock: asyncio.Lock | None = None,
                      tools: dict, confirm_callback,
                      stream_sink) -> ToolResult:
        """
        执行单个 LLM 请求的工具调用，内部处理所有异常。

        流程(中间件管道)::

            0. 发射 tool_start 事件（门控 stream_sink；带工具名与已解析参数）
            1. 构造 ToolContext（trace_id / session_id / agent_type / 工具 / 参数）
               —— ctx 在参数解析前构造，保证所有路径都能走 after 链审计
            2. _run_parsed 走解析后的管道：
               a. 解析 JSON 参数（失败 → 走 after 链 → 错误 ToolResult）
               b. 非 dict 参数归一化为 {}（防止 ** 展开崩溃，审计记录空参数）
               c. 写类工具采样目标旧文本（diffstat 徽标数据源）
               d. 未知工具（不存在 → 走 after 链 → 错误 ToolResult）
               e. before 阶段：顺序执行各中间件的 before 钩子
                  - 抛 ConfirmRequired → 调用 confirm_callback 决策：
                    拒绝 → user_denied ToolResult；通过 → 执行工具
                  - 抛其他 SecurityError → security_blocked ToolResult
               f. 执行工具（异常 → ToolResult(text="Tool error: ...")）
               g. after 阶段：逆序执行各中间件的 after 钩子（洋葱模型）
            3. finally 收口发射恰好一条 tool_end 事件（耗时 + 写类 diffstat +
               completion/错误兜底文本）——正常/异常/拦截/解析失败全覆盖

        注意:JSON 解析失败和未知工具不绕过中间件管道——ctx 在解析前构造,
        早退路径也走 after 链(仅审计),保证这些异常路径同样留下审计痕迹
        (工具为 None 时各中间件 before 钩子不执行,只有审计记录调用)。

        错误处理采用"降级为文本"策略:所有异常(JSON 解析失败、未知工具名、工具
        执行异常、中间件拦截)都转为 ToolResult(text="..."),作为正常对话流的一部分
        反馈给 LLM。LLM 在下一轮中看到错误文本后可自行决定重试、调整参数或放弃。

        Args:
            tool_call: LLM 返回的工具调用字典 {"id": str, "function": {"name": str,
                "arguments": str}}，其中 arguments 为 JSON 字符串，本方法负责解析
            trace_id: 本次 run 的追踪 ID，写进 ToolContext 并决定运行期容器
            turn: ReAct 轮次，注入审计条目供跨轮回溯
            confirm_lock: 并发确认串行锁（asyncio.Lock | None）。同一 message 的多个
                工具调用并发执行时由调用方传入同一个锁，把确认回调调用串行化（CLI
                标准输入并发读会竞态）；None = 非并发路径
            tools: dict，本次调用的工具表（调用方现取——它可能被整表替换）
            confirm_callback: 用户确认回调（调用方现取——spawn 会把它包一层）
            stream_sink: 事件回调（调用方现取——Web 适配层在装配之后才注入）；None 时
                零开销：既不解析参数用于展示，也不发事件

        Returns:
            ToolResult，始终返回（不抛异常）

        """
        name = tool_call["function"]["name"]

        # 0. 发送工具调用开始事件（流式渲染）
        # 目的：在参数解析前就发出事件，这样即使后续 JSON 解析失败或未知工具，
        # 终端渲染器也能及时清空中间内容缓冲区，避免把思考文本误判为最终答案。
        # 事件只带已解析的原始参数（tool_name + args），活动行摘要与调用行由终端
        # 层现算——引擎不做排版。参数非法或为空时传 None，终端显示纯工具名。
        # 门控：仅当挂了 stream_sink 时才执行（即 CLI 交互模式），否则零开销。
        if stream_sink is not None:
            try:
                parsed_args = json.loads(tool_call["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                parsed_args = None
            if not isinstance(parsed_args, dict) or not parsed_args:
                parsed_args = None
            stream_sink(AgentEvent(
                AgentEventKind.TOOL_START, "", self._agent_type,
                tool_name=name, args=parsed_args))

        # 1. 按工具名查找 Tool 实例
        # 若 tools 中无此名称，说明 LLM 幻觉或受提示注入攻击生成了非法工具名。此时 tool = None，后续会处理并返回错误 ToolResult。
        tool = tools.get(name)

        # 2. 构建 ToolContext（工具调用上下文对象）
        # 提前构造 ctx 是设计关键：即使参数解析失败或工具不存在，也要能够执行 after 钩子（审计、日志等），保证所有执行路径都有审计记录。
        # ctx 会贯穿整个管道，中间件可在 before/after 中读写其属性（如添加额外元数据、修改结果等）。
        ctx = ToolContext(
            trace_id=trace_id,
            session_id=self._session_id,
            user_id=getattr(self, "_user_id", None),
            agent_type=self._agent_type,
            tool=tool,
            tool_name=name,
            tool_call_id=tool_call.get("id") or "",
            timestamp=datetime.now().isoformat(),
            started_at=time.monotonic(),
            turn=turn,
        )

        try:
            return await self._run_parsed(tool_call, ctx, tool, tools,
                                      confirm_callback, confirm_lock, turn)
        finally:
            # tool_end 恰好一条：正常/异常/拦截/解析失败都经 finally 收口
            if stream_sink is not None:
                stream_sink(self._tool_end_event(ctx))

    async def _run_parsed(
        self, tool_call: dict, ctx: ToolContext, tool, tools,
        confirm_callback, confirm_lock, turn
    ) -> ToolResult:
        """解析后的管道；tool_end 收口在调用方 finally。

        Args:
            tool_call: dict，工具调用（含 function.arguments）
            ctx: ToolContext，调用上下文
            tool: Tool | None，命中的工具实例
            tools: dict，本次调用的工具表（写互斥拒绝时给模型回报可用工具）
            confirm_callback: 用户确认回调（本次调用现取）
            confirm_lock: asyncio.Lock | None，确认串行锁
            turn: int，当前轮次

        Returns:
            该次工具调用的 ToolResult（解析失败/未知工具/被拦截都降级为结果文本）。
        """

        # 3. 解析 JSON 参数
        # LLM 生成的 arguments 是 JSON 字符串，必须解析为 dict。
        # 若解析失败（非法 JSON），记录错误到 ctx，执行 after 钩子，然后返回带有解析错误的 ToolResult，让 LLM 自己决定是否重试。
        try:
            raw_args = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError as e:
            # LLM 生成了非法 JSON → 走 after 链记录审计后反馈给 LLM
            ctx.error = e
            await self._run_after_hooks(ctx)
            return ToolResult(text=f"Tool argument parse error: {e}")

        # 4. 参数归一化
        # 如果 raw_args 不是 dict（例如 LLM 生成了数组或字符串），为了安全将其归一化为空字典 {}，防止后续 tool.execute(**ctx.args) 时展开崩溃。
        # 这种异常情况也会被记录在 ctx.args 中供审计。
        ctx.args = raw_args if isinstance(raw_args, dict) else {}

        # 资源引用形状校验：畸形 id/文件名在进内部 HTTP 前就拒绝，避免白跑一次网络。
        violations = validate_ref_args(tool, ctx.args) if tool is not None else []
        if violations:
            ctx.error = ValueError("资源引用非法")
            await self._run_after_hooks(ctx)
            detail = "；".join(
                f"{v['param']}={v['value']!r}（{v['reason']}）" for v in violations)
            return ToolResult(text=f"参数非法：{detail}", is_error=True)

        # 写入互斥与版本冲突由 Java 的 bio_file.version 条件更新裁决；Python 侧只保留
        # 确认回调的串行锁（confirm_lock），不再按本地路径排队或登记写占用。
        return await self._run_guarded(
            tool, ctx, tools, confirm_callback, confirm_lock, turn)

    async def _run_guarded(self, tool, ctx, tools, confirm_callback,
                           confirm_lock, turn) -> ToolResult:
        """确认与执行段：同路径锁保护下运行。

        Args:
            tool: Tool | None，命中的工具实例
            ctx: ToolContext，调用上下文
            tools: dict，本次调用的工具表（未知工具时回报可用清单）
            confirm_callback: 用户确认回调（本次调用现取）
            confirm_lock: asyncio.Lock | None，确认串行锁
            turn: int，当前轮次

        Returns:
            该次工具调用的 ToolResult（含 before 拦截结果与执行结果）。
        """

        # 5. 处理未知工具（LLM 幻觉或 prompt injection）
        # 若工具不存在（tool is None），记录错误，执行 after 钩子，并返回可用工具列表，帮助 LLM 纠正。
        # 注意：此时不会执行 before 钩子（因为无工具可执行），但 after 钩子仍会运行，确保审计覆盖。
        if tool is None:
            ctx.error = ValueError(f"Unknown tool: {ctx.tool_name}")
            await self._run_after_hooks(ctx)
            return ToolResult(
                text=f"Unknown tool: {ctx.tool_name}. Available: {list(tools.keys())}"
            )

        # 6. before 阶段：顺序执行所有安全中间件的 before 钩子。
        result = await self._run_before_hooks(ctx, confirm_lock, confirm_callback)
        if result is not None:
            # 若 before 阶段返回了 ToolResult（拒绝/拦截），直接返回给 LLM
            return result

        # 7. 执行工具逻辑（结果统一规范化为 ToolResult）
        # 经过 before 阶段后，确认工具可以执行。
        # 使用 asyncio.to_thread 将工具放到线程池执行，避免阻塞事件循环。
        # 对于 CPU/网络密集型操作，这能保证并发调度不被单个长耗时任务阻塞。
        #
        # 特殊处理：若工具声明了 wants_run_state=True（搜索去重池与写盘类工具），则注入一个按 trace_id 键控的运行期容器（_run_state），用于跨调用共享已访问的 URL、产物账本等在途状态。
        # 该注入通过额外参数 _run_state 传递，不写入 ctx.args，因为 ctx.args 会被序列化用于审计，而该容器不可序列化。
        try:
            # spawn 等异步原生工具：await tool.aexecute(...)，父事件循环上直接 await
            # asyncio.to_thread 把同步 execute 丢进线程池跑。这对普通工具没问题，但对 spawn 是致命的：asyncio 取消不了线程。
            # 用户按 Ctrl+C 时，事件循环收到 CancelledError，to_thread 的 future 被取消，
            # 但已经在线程里跑起来的子 agent 会继续跑完——留下一个孤儿线程，继续烧 LLM token、继续写文件，用户以为已经停了。
            #
            # aexecute 构造子 Agent 后，通过 _run_child 在父的事件循环上 await child.run(task)。
            # asyncio 的取消是协作式的，沿 await 链传播：父 run() 被取消 →
            # CancelledError 传入 spawn 调用点的这个 await →
            # 进入 _run_child（其 docstring 明确写了“取消传播给子任务，再原样上抛”）→
            # 子 agent 的 run() 也被取消。整棵 agent 树一起退出，不需要任何额外的清理逻辑。
            if getattr(tool, "async_execute", False):
                # 异步工具（如 spawn）：在当前事件循环上直接 await——子 agent 与父
                # 同循环，父被取消（Ctrl+C）时 CancelledError 沿 await 链级联传播，
                # 整棵 agent 树一起终止，不再经 to_thread 留孤儿线程。
                raw = await tool.aexecute(**ctx.args)

            # 需要运行期状态的工具（搜索去重池 / 写盘产物登记）：注入本次 run 的容器。
            # 子 agent 继承父 trace_id，所以同一用户任务内跨 agent 共享同一个容器。
            elif getattr(tool, "wants_run_state", False):
                raw = await asyncio.to_thread(
                    tool.execute, **ctx.args, _run_state=get_run_state(ctx.trace_id))

            # 普通同步工具：asyncio.to_thread(execute, ...)
            else:
                raw = await asyncio.to_thread(tool.execute, **ctx.args)
            ctx.result = raw if isinstance(raw, ToolResult) else ToolResult(text=str(raw))
        except Exception as e:
            # 工具执行失败（网络超时、文件不存在等）→ 反馈给 LLM
            ctx.error = e
            ctx.result = ToolResult(text=f"Tool error: {e}")

        # 8. after 阶段（逆序 = 洋葱模型，后注册的中间件先看到结果）
        await self._run_after_hooks(ctx)
        # 9. 大结果外置：after 钩子已看到原文，模型只看到指针。
        #    外置失败时保留原结果（降级为完整文本），不阻断工具调用。
        if self._offloader is not None and ctx.result is not None:
            try:
                ctx.result = await asyncio.to_thread(
                    self._offloader, ctx.tool_name, ctx.tool_call_id,
                    ctx.session_id, ctx.result, tool, ctx.user_id)
            except Exception as e:
                print(f"[tool offload] failed: {e}", file=sys.stderr)
        # 完成摘要（写/编辑工具）不再单独发事件：并入调用方 finally 收口的
        # tool_end 事件文本（_tool_end_event），保证每条工具调用恰好一条收口。
        return ctx.result

    def _tool_end_event(self, ctx: ToolContext) -> AgentEvent:
        """tool_end 事件：耗时 + 写类 diffstat + 结果文本（结构化，不排版）。

        completion 与 error 都原样上报，由终端决定这一行怎么显示——引擎不拼
        "Tool failed: …" 这类文案。diffstat 是例外：±行数需要「写盘前的旧文本」
        这一现场（在 before 钩子之前采样），写完就取不回来了，终端事后算不出，
        故只能在这里算好。

        Args:
            ctx: ToolContext，本次工具调用上下文

        Returns:
            tool_end 事件（耗时 + 写类 diffstat + completion/error 原文）。
        """
        duration = (int((time.monotonic() - ctx.started_at) * 1000)
                    if ctx.started_at is not None else None)
        # 文档正文在 OSS，diffstat 不再采样本地文件；终端只显示工具完成文本。
        diffstat = None
        completion = (ctx.result.completion
                      if ctx.result is not None and ctx.result.completion else None)
        return AgentEvent(AgentEventKind.TOOL_END, "", self._agent_type,
                          tool_name=ctx.tool_name or None,
                          args=ctx.args if isinstance(ctx.args, dict) and ctx.args else None,
                          completion=completion,
                          error=str(ctx.error) if ctx.error is not None else None,
                          duration_ms=duration, diffstat=diffstat)

    async def _run_before_hooks(self, ctx: ToolContext,
                               confirm_lock: asyncio.Lock | None = None,
                               confirm_callback=None) -> ToolResult | None:
        """顺序执行所有安全中间件的 before 钩子。
        每个中间件可以：
          - 正常返回：放行，继续下一个中间件
          - 抛出 ConfirmRequired：需要用户确认（高风险操作）
          - 抛出 SecurityError（或其子类）：策略拦截（如拒绝访问敏感文件）

        若所有钩子通过，返回 None，表示可以继续执行工具。
        若中途拦截（用户拒绝、策略阻止），则返回一个 ToolResult，调用方应直接返回该结果，不再执行工具。

        内部处理：
            - 捕获 ConfirmRequired → 调用确认回调（串行化），记录审批事件
            - 捕获 SecurityError → 直接返回策略拒绝的 ToolResult

        Args:
            ctx: ToolContext，调用上下文
            confirm_lock: asyncio.Lock | None，确认串行锁

        Returns:
            None 表示全部通过可执行工具；否则返回拦截/拒绝的 ToolResult。
        """
        for mw in self._middleware:
            try:
                await mw.before(ctx)
            except ConfirmRequired as cr:
                # except 变量在块尾会被 Python 隐式删除，闭包里改用提前绑定的名字
                confirm_req = cr
                # ----- 需要用户确认 -----
                # 先通知中间件“请求已发出”
                for mw in self._middleware:
                    await mw.on_approval(ctx, "requested")

                # 定义异步决策函数，调用外部确认回调
                async def _decide() -> bool:
                    """调用外部确认回调获取用户决策。

                    Returns:
                        True 表示用户放行。
                    """
                    return await confirm_callback(confirm_req)

                # 串行化确认（若提供了锁）
                try:
                    if confirm_lock is not None:
                        async with confirm_lock:
                            confirmed = await _decide()
                    else:
                        confirmed = await _decide()
                except asyncio.CancelledError:
                    # 取消路径审计闭环：approval_requested 已发出但决策
                    # 未落——显式结算为 cancelled 后再抛，审计不再出现「有 requested
                    # 无 decided」的悬空；确认集合不加键（下次同路径仍会询问）。
                    for mw in self._middleware:
                        await mw.on_approval(
                            ctx, "decided",
                            approval_outcome=ApprovalOutcome.CANCELLED)
                    raise

                # 根据确认结果和是否有人工回调，标记决策类型
                # 决策语义:确认通过 → user_confirmed;被拒时按是否有真实人工回调区分
                # user_denied / auto_denied(fail-safe 默认拒绝,无人值守)。
                outcome = (
                    ApprovalOutcome.USER_CONFIRMED if confirmed else (
                        ApprovalOutcome.USER_DENIED if self._has_human_confirm
                        else ApprovalOutcome.AUTO_DENIED))
                ctx.approval_outcome = outcome

                # 通知中间件决策已做出
                for mw in self._middleware:
                    await mw.on_approval(ctx, "decided", approval_outcome=outcome)

                if not confirmed:
                    # 拒绝 → 记录错误并走 after 钩子，反馈给 LLM
                    # 注意：此时工具尚未执行，但 after 钩子仍会运行以记录审计。
                    # summary.decision 用已计算的 outcome（user_denied/auto_denied），
                    # 与 ctx.approval_outcome 保持一致——拒绝路径带决策依据回放给 LLM
                    ctx.error = cr
                    await self._run_after_hooks(ctx)
                    return ToolResult(
                        text=f"User denied: {cr.tool_name}",
                        summary={SUMMARY_DECISION: outcome, "tool": cr.tool_name},
                    )

                # 确认通过：标记 ctx，继续执行（不返回，后续会执行工具）
                cr.confirm()
                ctx.user_confirmed = True
            except SecurityError as se:
                # ContentGuardMiddleware / WorkspacePolicyMiddleware /
                # CommandGuardMiddleware 抛出的 security_blocked → 带决策摘要返回
                ctx.error = se
                await self._run_after_hooks(ctx)
                return ToolResult(
                    text=f"{se.decision}: {se.reason}",
                    summary={SUMMARY_DECISION: se.decision,
                             SUMMARY_VIOLATIONS: getattr(se, "violations", [])},
                )
        # 全部通过
        return None

    async def _run_after_hooks(self, ctx: ToolContext) -> None:
        """逆序执行所有中间件的 after 钩子（洋葱模型）。

        无论工具是否执行成功、无论是否被 before 拦截，
        只要进入了管道（ctx 已构建）就会执行 after，
        保证审计等横切关注点在所有路径上都能记录。

        Args:
            ctx: ToolContext，调用上下文（含结果或异常）
        """
        for mw in reversed(self._middleware):
            try:
                await mw.after(ctx)
            except Exception as e:
                # 审计等 after 钩子失败不应中止工具执行结果返回
                print(f"[security] after hook {type(mw).__name__} failed: {e}", file=sys.stderr)
