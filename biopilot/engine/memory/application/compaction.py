"""上下文压缩：对话超窗时压缩 in-context 窗口（驱逐旧对话 + 插摘要）。

作用于 agent 的 in-context 窗口：保留冻结的历史摘要段、追加一份新摘要，
再按 keep 配置保留近期尾部。只改窗口，绝不删 SQL 原始消息（历史仍完整
留在库中供审计/排障，但不再提供会话检索回溯）。

摘要固定 10 节：前 8 节是叙述，第 9 节硬约束（逐字抄录用户原话）、第 10 节
截止时间（只在用户明确说过时出现）。全部由模型生成；除第 9 节外，用户原话
不进摘要，也不作回溯。
输出受 summary_max_words 总预算约束：超支时带具体 token 数作为反馈重调
一次，渲染层按节份额水填保证「10 节齐全 + 总量合规」。
旧摘要并入下一次摘要输入重摘（集成指令约束漂移）：窗口
恒只有一份最新摘要，多次压缩不累积。
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace

from biopilot.config.sections import CompactionSettings, ContextSize
from biopilot.engine.llm import Message, SystemMessage, UserMessage
from biopilot.common.utils.tokenization import get_token_encoder
from biopilot.engine.memory.domain.entity.summary import Summary

__all__ = ["CompactionSettings", "ContextSize", "estimate_tokens",
           "blend_token_ratio", "should_compress", "run_compaction",
           "deterministic_trim"]

logger = logging.getLogger(__name__)

#: 摘要的开场标记（续接说明）；UserMessage 以此识别。
_SUMMARY_MARKER = (
    "This session is being continued from a previous conversation that ran out of context.")
#: 摘要的完整开场白；后面接 10 节正文。
_SUMMARY_OPENING = (
    f"{_SUMMARY_MARKER}\n"
    "The summary below covers the earlier portion of the conversation...\n\n"
)
#: 摘要正文里的中文可见标记（不是识别依据，只供人读）。
_SUMMARY_LABEL = "[对话摘要]"

#: 每条消息的协议开销（3 条消息框架 + 1 个角色名，对齐 OpenAI 的计数口径）。
_PROTOCOL_OVERHEAD = 4

#: 校准系数的夹紧区间与 EMA 权重：单次观测可能偏得离谱（缓存命中、端点口径差异），
#: 夹紧后折半并入，不让一次异常带偏整体。
_RATIO_MIN, _RATIO_MAX = 0.5, 2.0
_RATIO_WEIGHT = 0.5

#: 摘要各节的正文份额（占「总预算 − 节标题开销」）。6/7/8/10 节内容天然短小；
#: 第 9 节是硬约束逐字保留的载体，留出与正文相当的份额，避免被叙述挤掉。
#: 份额只是渲染层的内部分配策略，不进提示词——模型只面对总预算。
_SECTION_SHARES: tuple[tuple[str, float], ...] = (
    ("1. Primary Request and Intent", 0.17),
    ("2. Key Technical Concepts", 0.12),
    ("3. Files and Code Sections", 0.16),
    ("4. Errors and fixes", 0.12),
    ("5. Problem Solving", 0.12),
    ("6. Pending Tasks", 0.08),
    ("7. Current Work", 0.04),
    ("8. Optional Next Step", 0.03),
    ("9. Hard Constraints", 0.13),
    ("10. Deadline", 0.03),
)

#: 节内容超预算时追加的标记；标记本身计入预算，总量不变量不被破坏。
_TRUNCATION_MARKER = "…（本节已按预算截断）"

#: 摘要超支时的带反馈重调次数；重调仍违规由渲染层水填兜底。
_SUMMARY_FEEDBACK_RETRIES = 1


def _is_summary(message: Message) -> bool:
    """判断一条消息是否是压缩摘要。

    摘要统一是 `UserMessage`，内容以固定的续接开场白开头；旧版
    `SystemMessage` 摘要已确认不存在于本地库，不再保留兼容分支。

    Args:
        message: 待判断的消息。

    Returns:
        True 表示这是摘要消息，不参与触发计数与近期尾部保留。
    """
    return (message.role == "user"
            and (message.content or "").startswith(_SUMMARY_MARKER))


def estimate_tokens(messages: list[Message]) -> int:
    """粗估消息 token 总量：逐条算正文与工具调用，再加协议开销。

    协议开销固定 4（3 条消息框架 + 1 个角色名，对齐 OpenAI 的计数口径），不按角色
    分档——分档只会得到一桌拍出来的常数，真正的偏差在别处（工具调用的 JSON 此前
    完全没算，而 arguments 常是一整段内容）。

    视觉 content parts 只计其中的文本部分：图片 token 由模型侧按块决定，本地算不出来。

    Args:
        messages: 消息列表（Message 家族）。

    Returns:
        估算的总 token 数（整数）。
    """
    total = 0
    # 编码器单点在 common.utils.tokenization（与 rag 切块共用同一口径）。
    enc = get_token_encoder()
    for m in messages:
        total += len(enc.encode(_countable_text(m))) + _PROTOCOL_OVERHEAD
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            total += len(enc.encode(json.dumps(tool_calls, ensure_ascii=False)))
    return total


def _countable_text(m: Message) -> str:
    """取一条消息里可计数的文本：正文为字符串时就是它，content parts 时只取文本部分。

    Args:
        m: 一条消息。

    Returns:
        用于 token 计数的文本（图片等非文本部分为空）。
    """
    content = m.content
    if content is None or isinstance(content, str):
        return content or ""
    return "".join(part.get("text", "") for part in content
                   if isinstance(part, dict) and part.get("type") == "text")


def blend_token_ratio(current: float, actual_prompt_tokens: int | None,
                      estimated_prompt_tokens: int | None) -> float:
    """用一次真实用量校准「本地估算 → 云端实际」的比例（EMA + 夹紧）。

    本地估算只能逼近，偏差是系统性的（口径不同、工具定义不计入正文等），故拿上一次
    请求的真实 ``prompt_tokens`` 除以当时的本地估算，得到一个乘数。出现三种情况时
    原样返回当前系数：没有真实用量（端点不报、流式未开 include_usage）、没有当时的
    估算、或估算为 0。

    单次观测先夹紧在 [0.5, 2.0]——缓存命中、端点计数口径差异都可能让某一次偏得很远，
    不该让它带偏整体；再用 EMA 折半并入（内容结构每轮都在变，不直接把系数打到观测值）。

    Args:
        current: 当前系数（初始 1.0 = 不校准）。
        actual_prompt_tokens: 上一次请求端点上报的输入 token 数。
        estimated_prompt_tokens: 上一次请求发送前的本地估算。

    Returns:
        新的校准系数。
    """
    if not actual_prompt_tokens or not estimated_prompt_tokens:
        return current
    observed = actual_prompt_tokens / estimated_prompt_tokens
    observed = min(max(observed, _RATIO_MIN), _RATIO_MAX)
    return (1 - _RATIO_WEIGHT) * current + _RATIO_WEIGHT * observed


def should_compress(messages: list[Message], settings: CompactionSettings,
                    context_window: int, *, estimate: int | None = None,
                    ratio: float = 1.0) -> bool:
    """判断当前窗口是否该压缩：任一 trigger 条件满足即触发（OR 逻辑）。

    messages 类型数非摘要消息条数；tokens 直接比估算值；fraction 比
    ``value × 有效窗口``。不再叠加固定的 1.1 安全边际——余量由 fraction 承担。

    Args:
        messages: 当前 in-context 消息列表。
        settings: 压缩配置（含 trigger / keep 等）。
        context_window: 模型的实际上下文窗口大小（token 数）。
        estimate: 已算好的消息 token 估算；None 表示现算。
        ratio: 校准系数（见 ``blend_token_ratio``），1.0 = 沿用本地估算原值。

    Returns:
        True 表示应触发压缩，False 表示无需压缩。
    """
    if not settings.enabled:
        return False
    ctx_size = settings.resolve_context_size(context_window)
    if estimate is None:
        estimate = estimate_tokens(messages)
    effective = estimate * ratio
    # 摘要是压缩产物，不是新的对话轮次，不参与 messages 触发计数。
    non_summary_count = sum(1 for m in messages if not _is_summary(m))
    for trigger in settings.trigger:
        if trigger.type == "messages":
            if non_summary_count >= trigger.value:
                return True
        elif trigger.type == "tokens":
            if effective >= trigger.value:
                return True
        elif trigger.type == "fraction":
            if effective >= trigger.value * ctx_size:
                return True
    return False


async def run_compaction(messages: list[Message], settings: CompactionSettings,
                         structured, summary_text: str | None = None,
                         context_window: int | None = None,
                         summary_structured=None) -> list[Message] | None:
    """执行压缩：旧摘要并入重摘 + 保留近期尾部 + 追加新摘要。

    这是压缩的唯一入口：生成摘要、摘要失败后的确定性降级都在这里完成；
    调用方只负责决定何时触发、把返回的新窗口写回。摘要文本可由调用方传入
    （测试/已有 summary），否则由 StructuredOutput 生成。压缩只改 in-context
    窗口；SQL 原始消息由 MessageManager 保留（供审计/排障，不提供会话检索回溯）。

    Args:
        messages: 当前 in-context 消息列表（将被子集替换）。
        settings: 压缩配置（含 trigger / keep / 摘要参数等）。
        structured: StructuredOutput 实例，用于生成摘要。
        summary_text: 可选预生成摘要；若为 None 则调用 _summarize 生成。
        context_window: 模型上下文窗口大小（用于计算 keep 的 fraction 预算）。
        summary_structured: 摘要专用 StructuredOutput；None 时用 structured。

    Returns:
        压缩后的新消息列表；摘要生成失败且未触发降级时返回 None。
    """
    if not settings.enabled:
        return None

    # 1. 本次要压的是「旧摘要（如有）+ 上次压缩之后的对话」：旧摘要作为重摘
    #    底稿一起送回摘要模型，由集成指令约束漂移。窗口因此恒只有一份最新
    #    摘要，多次压缩不累积。
    if not messages:
        return None

    if summary_text is None:
        # 摘要由一次结构化调用产出；失败时按窗口是否已超硬上限决定是否做
        # 确定性降级，避免把一次模型失败直接变成超窗请求。
        result = await _summarize(
            messages, summary_structured or structured, settings)
        if result is None:
            ctx = settings.resolve_context_size(context_window or 0)
            hard_limit = 0.95 * ctx if ctx > 0 else 0
            if hard_limit and estimate_tokens(messages) >= hard_limit:
                return deterministic_trim(messages, settings, context_window)
            return None
        summary_text = _render_summary(result, settings.summary_max_words)

    if not summary_text:
        return None

    # 2. 尾部按 keep 配置保留；没留下的消息就是本次摘要覆盖的「旧段」。
    #    顺序固定为：新摘要 → 近期尾部（旧摘要不重复保留，它已被新摘要取代）。
    tail = _recent_tail(messages, settings, context_window)
    summary_message = UserMessage(content=_ensure_summary_envelope(summary_text))
    new_window = [summary_message] + tail
    # 后置检查：压缩后窗口若仍满足触发条件，说明「摘要 + 尾部」之和降不到
    # 触发线以下——keep=messages 时尾部按条数计、token 无上界。
    # 只暴露问题不自动行为；连环出现应检查 keep 配置或工具结果外置阈值。
    if context_window and should_compress(new_window, settings, context_window):
        logger.warning(
            "压缩后窗口仍满足触发条件（约 %d token）：尾部与累积摘要过大，"
            "连续出现请调整 keep 配置或工具结果外置阈值",
            estimate_tokens(new_window))
    return new_window


def deterministic_trim(messages: list[Message], settings: CompactionSettings,
                       context_window: int | None = None) -> list[Message] | None:
    """摘要连续失败且窗口超过硬上限时的确定性降级。

    保留全部冻结摘要段与配置的近期尾部，把中间被移出的消息数写成一条明确
    占位；不调 LLM，因此恢复不依赖另一次成功的模型调用。没有可移出的消息
    时返回 None。

    Args:
        messages: 当前 in-context 窗口。
        settings: 压缩配置（keep / context_size）。
        context_window: 模型上下文窗口（推导 0.8 预算）。

    Returns:
        降级后的窗口；没有可移出内容时返回 None。
    """
    summaries = [m for m in messages if _is_summary(m)]
    rest = [m for m in messages if not _is_summary(m)]
    ctx = settings.resolve_context_size(context_window or 0)
    budget = int(0.8 * ctx) if ctx > 0 else 0
    trim_settings = (replace(settings, keep=ContextSize("tokens", budget))
                     if budget > 0 else settings)
    tail = _recent_tail(rest, trim_settings, context_window)
    dropped = len(rest) - len(tail)
    if dropped <= 0:
        return None
    placeholder = SystemMessage(content=(
        f"[压缩失败：较早的 {dropped} 条消息已移出窗口；原文不回溯]"))
    return summaries + [placeholder] + tail


def _ensure_summary_envelope(text: str) -> str:
    """确保摘要文本以固定的续接开场白开头；已带开场白则原样返回。

    Args:
        text: 摘要正文。

    Returns:
        带完整开场白的摘要内容。
    """
    if text.startswith(_SUMMARY_MARKER):
        return text
    return f"{_SUMMARY_OPENING}{_SUMMARY_LABEL}\n{text}"


def _recent_tail(messages: list[Message], settings: CompactionSettings,
                 context_window: int | None = None) -> list[Message]:
    """按 keep 配置从后往前保留近期上下文。

    keep 支持三种计量：messages（条数）、tokens（绝对预算）、fraction
    （有效窗口比例）。两个关键约束不变：
    - 携带工具调用的 assistant 消息与其 tool 结果必须成对保留——孤立 tool 消息
      的 tool_call_id 无对应调用会触发 API 报错。
    - 成对逻辑之后再做一次孤儿清理兜底：tool 消息的 tool_call_id 必须在保留的
      assistant(tool_calls) 里找得到，否则丢弃（覆盖极端轨迹）。

    Args:
        messages: 待保留的消息列表（已排除摘要段与头部 system）。
        settings: 压缩配置（含 keep, context_size）。
        context_window: 模型上下文窗口（用于推导 fraction 预算）。

    Returns:
        保留的尾部消息列表（保持原有顺序）。
    """
    ctx_size = settings.resolve_context_size(context_window or 0)
    keep = settings.keep
    if keep.type == "messages":
        count_limit: int | None = int(keep.value)
        token_budget: int | None = None
    else:
        count_limit = None
        token_budget = (int(keep.value) if keep.type == "tokens"
                        else int(keep.value * ctx_size))

    kept: list[Message] = []
    used = 0
    count = 0
    for m in reversed(messages):
        # 跳过 system 消息与摘要（摘要由调用方单独保留）
        if m.role == "system" or _is_summary(m):
            continue
        cost = estimate_tokens([m])
        if count_limit is not None:
            if count >= count_limit and kept:
                break
        elif token_budget is not None:
            if used + cost > token_budget and kept:
                break
        used += cost
        count += 1
        if any(m is k for k in kept):
            continue
        kept.append(m)

        # 若当前消息是 tool 消息，把关联的 assistant(tool_calls) 一并保留，
        # 保证 tool_call_id 在尾部里有对应调用。
        if m.role == "tool":
            for prev in reversed(messages[: messages.index(m)]):
                if prev.role == "assistant" and prev.tool_calls:
                    if prev not in kept:
                        kept.append(prev)
                    break

    result = list(reversed(kept))
    seen_tool_ids = {tc["id"] for m in result if m.role == "assistant" and m.tool_calls
                     for tc in m.tool_calls}
    return [m for m in result
            if not (m.role == "tool" and m.tool_call_id not in seen_tool_ids)]


_SUMMARY_PROMPT = """You are compressing a research assistant conversation into a structured summary.
Write in the user's language. Be specific: keep paper titles, file paths, tool names,
error messages, numbers, and decisions. Do not invent facts.

Return these summary fields. The numbers match the final 10-section summary:
1. primary_request_and_intent — the user's core request and success criteria.
2. key_technical_concepts — key concepts and domain terms.
3. files_and_code_sections — papers, notes, data paths, and script snippets involved.
4. errors_and_fixes — errors encountered and how they were fixed.
5. problem_solving — the problem-solving process and the reasons behind decisions.
6. pending_tasks — what remains to be done.
7. current_work — what was happening immediately before this summary.
8. optional_next_step — the next step directly in line with the user's most recent request.

9. hard_constraints — a list of must/must-not constraints, copied verbatim from the user.
   Preserve security- and authorization-relevant instructions exactly. Use [] when none.
10. deadline — only if the user explicitly stated one; otherwise null. Never infer it.

The conversation may begin with an earlier summary (a user message starting "This
session is being continued..."). Treat it as your working draft, not just source
material: integrate it — carry forward all still-relevant facts, decisions, and
numbers; never lose established constraints; where newer history supersedes older
information, keep the newer and drop the stale. The final summary must stand alone.

The WHOLE output — all 10 sections — MUST stay under {max_words} tokens in total.
Keep hard constraints verbatim even when that costs space elsewhere; shorten the
narrative sections instead. Never invent a constraint or a deadline.

Conversation to summarize:
<conversation>
{conversation}
</conversation>
"""


def _format_messages(messages: list[Message]) -> list[str]:
    """把待摘要消息格式化成可读行；user/assistant 截 2000 字符，tool 截 500。

    Args:
        messages: 待摘要的消息列表。

    Returns:
        每行一条消息的文本列表（保持原顺序）。
    """
    lines: list[str] = []
    for m in messages:
        content = (m.content or "").strip()
        if not content:
            continue
        label = m.role
        if m.role == "tool":
            # 指针消息只取预览：摘要不应携带 tool_call_id / 对象键等引用信息。
            try:
                pointer = json.loads(content)
                if isinstance(pointer, dict) and pointer.get("decision") == "persisted":
                    content = str(pointer.get("preview") or "")
            except (json.JSONDecodeError, TypeError):
                pass
            label = "tool"
        if _is_summary(m):
            # 旧摘要是重摘的底稿，逐条截断会削掉底稿，豁免截断。
            lines.append(f"{m.role}: {content}")
            continue
        limit = 500 if m.role == "tool" else 2000
        if len(content) > limit:
            content = content[:limit] + "…"
        lines.append(f"{label}: {content}")
    return lines


def _trim_lines(lines: list[str], budget: int) -> list[str]:
    """按 token 预算从最旧一行开始丢弃，至少保留一行。

    Args:
        lines: 格式化后的消息行。
        budget: 输入 token 上限；<=0 表示不裁剪。

    Returns:
        裁剪后的行列表。
    """
    if budget <= 0 or not lines:
        return lines
    enc = get_token_encoder()
    while len(lines) > 1 and len(enc.encode("\n".join(lines))) > budget:
        lines.pop(0)
    return lines


def _fit_budget(text: str, cap: int, enc) -> str:
    """把文本压到 token 预算内；超限时截断并附标记，标记本身计入预算。

    Args:
        text: 待截断的文本。
        cap: token 上限；标记长度从中扣除，保证结果总量不超。
        enc: token 编码器（调用方复用同一实例，避免重复加载）。

    Returns:
        预算内的文本；未超限时原样返回。
    """
    tokens = enc.encode(text)
    if len(tokens) <= cap:
        return text
    keep = max(0, cap - len(enc.encode("\n" + _TRUNCATION_MARKER)))
    return enc.decode(tokens[:keep]) + "\n" + _TRUNCATION_MARKER


def _render_summary(summary: Summary, max_words: int) -> str:
    """把模型写的 10 节内容水填成不超预算的完整摘要。

    预算记账：summary_max_words 先扣掉节标题的实际 token 开销，余下按
    _SECTION_SHARES 分给各节正文；内容短于份额的节把闲置预算水填给被截的
    节。两条不变量由构造保证——每节都进渲染循环（10 个标题恒在场）、每节
    ≤ 分得份额（总量 ≤ 预算）。极小预算连标题都放不下时完整性优先：
    原样渲染全部节，预算不变量让位于完整性。

    Args:
        summary: 模型生成的 10 节内容。
        max_words: 摘要总预算（token；开场白不计入）。

    Returns:
        10 节摘要正文（开场白由 run_compaction 统一包装）。
    """
    sections = [(title, (text or "").strip() or "（无）")
                for title, text in _summary_sections(summary)]
    enc = get_token_encoder()
    # 预算切分要计入全部结构性开销：节标题行、标题后的换行、节间空行——
    # 漏掉任何一项，总量不变量就会差几个 token。
    joiner = len(enc.encode("\n\n"))
    header_cost = (sum(len(enc.encode(f"## {title}\n")) for title, _ in sections)
                   + (len(sections) - 1) * joiner)
    body_budget = max_words - header_cost
    if body_budget <= 0:
        return "\n\n".join(f"## {title}\n{text}" for title, text in sections)

    caps = {title: int(body_budget * share)
            for title, share in _SECTION_SHARES}
    # 首轮：短节原样保留并交回闲置份额；超长节记下原长，等水填。
    overflow: dict[str, int] = {}
    leftover = 0
    for title, text in sections:
        cost = len(enc.encode(text))
        if cost <= caps[title]:
            leftover += caps[title] - cost
        else:
            overflow[title] = cost
    # 水填：闲置预算按被截节的原长比例回流。
    if overflow and leftover > 0:
        total = sum(overflow.values())
        for title, cost in overflow.items():
            caps[title] += int(leftover * cost / total)
    return "\n\n".join(
        f"## {title}\n{_fit_budget(text, caps[title], enc)}"
        for title, text in sections)


def _summary_sections(summary: Summary) -> list[tuple[str, str]]:
    """把模型写的 10 节排成 (标题, 正文) 列表；顺序与编号即最终摘要结构。

    Args:
        summary: 结构化输出里的摘要实体。

    Returns:
        渲染与预算校验共用的节列表。
    """
    return [
        ("1. Primary Request and Intent", summary.primary_request_and_intent),
        ("2. Key Technical Concepts", summary.key_technical_concepts),
        ("3. Files and Code Sections", summary.files_and_code_sections),
        ("4. Errors and fixes", summary.errors_and_fixes),
        ("5. Problem Solving", summary.problem_solving),
        ("6. Pending Tasks", summary.pending_tasks),
        ("7. Current Work", summary.current_work),
        ("8. Optional Next Step", summary.optional_next_step),
        ("9. Hard Constraints", _constraints_text(summary)),
        ("10. Deadline", _deadline_text(summary)),
    ]


def _constraints_text(summary: Summary) -> str:
    """把硬约束渲染成第 9 节正文：一条一行，原话不改写。

    Args:
        summary: 结构化输出里的摘要实体。

    Returns:
        逐条排列的硬约束；没有约束时返回空串，由渲染层补「（无）」占位。
    """
    constraints = [c.strip() for c in summary.hard_constraints if c.strip()]
    return "\n".join(f"- {c}" for c in constraints)


def _deadline_text(summary: Summary) -> str:
    """把截止时间渲染成第 10 节正文；没有说过时返回空串。

    Args:
        summary: 结构化输出里的摘要实体。

    Returns:
        截止时间原文；用户没说过截止时间时返回空串。
    """
    return (summary.deadline or "").strip()


def _budget_violations(result: Summary, body_budget: int) -> str:
    """检查一次结构化输出是否超预算，产出回喂模型的反馈文本。

    校验一项：10 节正文（含节标题）超总预算。反馈带具体 token 数字，供
    带反馈重调使用。

    Args:
        result: 模型的结构化输出。
        body_budget: 摘要 10 节的 token 上限。

    Returns:
        违规描述；完全合规时返回空串。
    """
    enc = get_token_encoder()
    body = "\n\n".join(
        f"## {title}\n{(text or '').strip() or '（无）'}"
        for title, text in _summary_sections(result))
    body_tokens = len(enc.encode(body))
    if body_tokens > body_budget:
        return (f"- The 10 summary sections render to {body_tokens} tokens, over the "
                f"{body_budget}-token budget. Compress the longest narrative "
                "sections; keep hard constraints verbatim.")
    return ""


async def _summarize(messages: list[Message], structured,
                     settings: CompactionSettings) -> Summary | None:
    """用结构化调用生成摘要；超支时带反馈重调一次。

    输出违反预算时，把具体数字作为反馈追加进 prompt 重调（最多
    _SUMMARY_FEEDBACK_RETRIES 次）。重调仍违规则交由渲染层兜底——逐节水填
    保证总量不变量，不无限重试。

    Args:
        messages: 待摘要的消息列表（旧摘要作为底稿一并参与）。
        structured: StructuredOutput 实例（支持 extract 方法）。
        settings: 压缩配置（含 trim_tokens_to_summarize / summary_max_words）。

    Returns:
        摘要结果；模型调用失败或摘要整体为空时返回 None。
    """
    if structured is None:
        return None
    # 摘要行豁免裁剪：_trim_lines 从最老的一端丢弃，而旧摘要恰在最老端，
    # 不豁免就会被先裁掉，重摘就没有底稿了。
    summary_msgs = [m for m in messages if _is_summary(m)]
    rest = [m for m in messages if not _is_summary(m)]
    lines = _trim_lines(_format_messages(rest),
                        settings.trim_tokens_to_summarize)
    if summary_msgs:
        lines = _format_messages(summary_msgs) + lines
    base_prompt = _SUMMARY_PROMPT.format(
        max_words=settings.summary_max_words,
        conversation="\n".join(lines) or "（无）",
    )
    result: Summary | None = None
    feedback = ""
    for attempt in range(_SUMMARY_FEEDBACK_RETRIES + 1):
        try:
            result = await structured.extract(
                prompt=base_prompt + feedback, schema=Summary)
        except Exception as exc:
            logger.warning("压缩摘要生成失败，窗口保持不变: %r", exc)
            return None
        violations = _budget_violations(result, settings.summary_max_words)
        if not violations:
            break
        if attempt < _SUMMARY_FEEDBACK_RETRIES:
            logger.info("压缩摘要超预算，带反馈重调: %s", violations)
            feedback = (
                "\n\nYour previous output violated the constraints below. "
                "Regenerate ALL fields of the JSON, fixing exactly these problems:\n"
                + violations)
    narrative_fields = (
        "primary_request_and_intent", "key_technical_concepts",
        "files_and_code_sections", "errors_and_fixes", "problem_solving",
        "pending_tasks", "current_work", "optional_next_step",
    )
    if not any(str(getattr(result, name)).strip()
               for name in narrative_fields):
        logger.warning("压缩摘要为空，窗口保持不变")
        return None
    return result
