"""MemoryConsolidator 记忆整合：把每轮对话沉淀进记忆块。

REPL 每轮对话结束后调 consolidate()：读取游标之后的新消息 + 全部可写块的当前
内容 → LLM 输出记忆编辑指令 → 全量预验证 → 经 BlockManager 应用进记忆块。喂入
旧值是「不产生矛盾条目」的前提——模型看不到旧内容就无从判断新信息推翻了哪一条。

产出是**行级**指令：新增一行 / 换掉某一行 / 删掉某一行，核心块另可整块重写；
没有值得沉淀的内容就返回空批次（NOOP，什么都不写）。目标块由代码按「类型 + 当天
日期」拼装（模型只给类型，不写日期）——同一类型同一天进同一分册，写满了续号。

旧行用**快照编号**定位：提示里的每行行首带一个跨分册的连续编号，模型只回填这个
整数，不必抄正文。编号与「块 + 整行原文」的对应关系在渲染提示时一并建立，应用时
按那份映射校验——块在 LLM 调用期间被别的写者改过，只会定位失败，不会删错行。
定位失败没有副作用，因此可以补一条修复轮；其它应用失败仍旧只跳过该条。
LLM 输出不可信，指令先过全量预验证（一条不过则整批不写）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from biopilot.core.memory.common.errors import (
    BlockLimitExceeded, MemoryEditTargetNotFound, MemoryEditValidationError)
from biopilot.core.memory.domain.dto.memory_edit import MemoryEdit
from biopilot.core.memory.domain.dto.memory_edit_batch import MemoryEditBatch

logger = logging.getLogger(__name__)

__all__ = ["MemoryConsolidator"]

#: 日期分册的块类型（label = `<类型>_<YYYY-MM-DD>`，写满续号 `<类型>_<YYYY-MM-DD>_2`）。
#: 核心块不参与分册——它们靠整块重写收敛。
_PREFIX_TARGETS = ("feedback", "project", "reference")

#: 可写块的 label 形态：两个核心块精确枚举 + 三类前缀家族（前缀之后是日期分册，
#: 也可能是早期按主题命名的块）。用来挑出「旧值要喂进 prompt」的块。
_WRITABLE_LABELS = frozenset({"profile", "assistant"})
_WRITABLE_PREFIXES = tuple(f"{target}_" for target in _PREFIX_TARGETS)

#: 连续失败多少次后强制推进游标：同一批坏编辑若反复失败，每个 REPL 轮次都会
#: 重新尝试，不推进就把管道卡死。推进即放弃这批消息（已如实记日志）。
_MAX_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True)
class _LineRef:
    """快照里的一行：编号指向的类型、承载它的块与整行原文。

    Attributes:
        target: str，该行所属的类型（profile/assistant/feedback/project/reference）
        label: str，承载该行的块 label
        text: str，该行原文；应用时按它校验，块被改写后不会动到别的行
    """
    target: str
    label: str
    text: str


def _today() -> str:
    """当天日期（YYYY-MM-DD）——分册键。

    由代码拼装而非让模型给：模型写错日期会让内容散进错误的分册。

    Returns:
        str，形如 YYYY-MM-DD。
    """
    return datetime.now().strftime("%Y-%m-%d")


def _is_writable_label(label: str | None) -> bool:
    """label 是否落在可写面上（决定哪些块的当前值要喂给整合器）。

    Args:
        label: str | None，块标签。

    Returns:
        bool，是核心块或三类前缀家族之一为 True。
    """
    if not label:
        return False
    return label in _WRITABLE_LABELS or label.startswith(_WRITABLE_PREFIXES)


def _target_of(label: str) -> str:
    """块 label → 目标类型（编号表按类型校验，防止拿别的类型的编号来改）。

    Args:
        label: str，块 label（核心块为自身名字，分册为 `<类型>_<日期>[_n]`）。

    Returns:
        str，目标类型；认不出时原样返回 label（调用方只在可写块上使用）。
    """
    for target in _PREFIX_TARGETS:
        if label.startswith(f"{target}_"):
            return target
    return label


def _describe_edit(edit: MemoryEdit) -> str:
    """把一条指令说成一句话（修复轮要告诉模型哪些已写入、哪些没定位到）。

    Args:
        edit: MemoryEdit，待描述的编辑指令。

    Returns:
        str，形如「add feedback「用户偏好短句」」或「drop project 第 3 行」。
    """
    if edit.action == "drop":
        return f"drop {edit.target} 第 {edit.line} 行"
    preview = edit.content.strip().replace("\n", " ")[:30]
    return f"{edit.action} {edit.target}「{preview}」"


def _edit_key(edit: MemoryEdit) -> tuple:
    """判重键：修复轮据此跳过上一批已经落地的指令（否则 add 会被重复写入）。

    编号刻意不参与 add/supersede 的键：修复轮会重新渲染编号，同一意图重发时编号
    已经变了，带着旧编号比对就判不出来重。两条 drop 的 content 都是空串，只有编号
    能区分它们指向哪一行，所以 drop 仍按编号判重。

    Args:
        edit: MemoryEdit，编辑指令。

    Returns:
        tuple，可比较的判重键。
    """
    if edit.action == "drop":
        return ("drop", edit.target, edit.line)
    return (edit.action, edit.target, edit.content.strip())


class MemoryConsolidator:
    """记忆整合器：把每轮对话沉淀进记忆块。

    触发是每轮一次（REPL 在本轮收尾调用）；进度由游标跟踪——游标值基于 messages
    表行数推导（不从内存计数器恢复），因此进程重启后从正确位置自愈：不重复整合
    已处理的消息、也不遗漏新增的消息。

    Attributes:
        agent_state: AgentState，提供 agent_id 供查询消息与推导游标
        block_manager: BlockManager，编辑指令最终落到它执行，也是旧记忆的来源
        message_manager: MessageManager，读对话消息与推导游标
        structured: StructuredOutput，LLM 抽取编辑指令的通道
        enable: bool，总开关
        _running: bool，本次整合是否在执行中（防并发重叠）
        _failures: int，连续失败计数（达阈值强制推进游标，防死循环）
        _cursor: int，已处理到的消息数游标（由 messages 表行数推导，进程重启可自愈）
    """

    def __init__(self, agent_state, block_manager, message_manager,
                 structured, enable: bool = False):
        """装配整合器依赖。

        Args:
            agent_state: AgentState 实例（supervisor 的 agent 状态），提供 agent_id
                供按会话查询消息、推导游标。
            block_manager: BlockManager，编辑指令最终映射到它执行（block CRUD），并读出全部
                可写块的旧值。
            message_manager: MessageManager，读对话消息、推导游标（size = 该会话
                消息总数）。
            structured: StructuredOutput，LLM 抽取编辑指令的通道；LLM 输出不可信，
                指令须经校验才应用。
            enable: 总开关；False 时 consolidate 直接返回（不调 LLM）。
        """
        self.agent_state = agent_state
        self.block_manager = block_manager
        self.message_manager = message_manager
        self.structured = structured
        self.enable = enable
        self._running = False
        self._failures = 0
        #: 已处理到的消息数量游标（基于 messages 表行数，从 DB 推导）
        #: 语义是“下次从游标处开始整合”
        self._cursor = self.message_manager.size(agent_state.agent_id) if message_manager else 0

    async def consolidate(self) -> None:
        """本轮收尾调用一次：有新消息就整合，没有就直接返回。

        三道廉价检查（未启用 / 已在跑 / 本轮无新增消息）任一成立即返回——
        空轮不调用 LLM。检查通过后执行一轮完整整合。
        """
        if not self.enable or self._running:
            return
        size = self.message_manager.size(self.agent_state.agent_id)
        if size <= self._cursor:
            return                      # 本轮没有新增消息：不调 LLM
        self._running = True
        try:
            await self._run_once()
        finally:
            self._running = False

    async def _run_once(self) -> None:
        """读取新消息 → LLM 编辑指令 → 全量预验证 → 逐条应用 → 结算 → 推进游标。

        各阶段失败面不同，处置也不同：

        1. **全量预验证**（_validate_edit）：任一编辑非法则**一条都不写**，并把
           MemoryEditValidationError 上抛给调用方（原子性）。
        2. **逐条应用**（_apply_batch）：单条失败**只跳过该条**、写日志后继续——
           一条坏编辑不该带走同批其余编辑。其中「编号定位不到旧行」无副作用，
           收尾时补一条修复轮让它有机会改正。
        3. **结算**（_cleanup_empty_shards）：清掉空分册；失败只记日志，不影响已落地的编辑。

        任何失败都写日志，绝不静默。游标是否推进取决于「这批消息有没有被消费」：一条
        编辑都没落盘时保留游标重试（连败达 _MAX_CONSECUTIVE_FAILURES 次才强制推进防
        死锁）；已有编辑落盘时照常推进——重放会产生重复写入。
        """
        new_msgs = self.message_manager.get_messages_by_agent_id(
            self.agent_state.agent_id)

        # 从游标处切出尚未整合的新消息。
        # 游标可能超前于当前总行数（如消息被清理或上次连败强制推进），此时切片为空，
        # 需校准游标，避免下次重复计算空区间。
        new_msgs = new_msgs[self._cursor:]
        if not new_msgs:
            self._cursor = self.message_manager.size(self.agent_state.agent_id)
            return

        prompt, refs = self._build_prompt(new_msgs)
        try:
            # 阶段 1：抽取 + 全量预验证——任一非法则整体失败，一条都不写
            batch = await self._extract_batch(prompt)
        except MemoryEditValidationError as e:
            # 原子性失败：不吞掉、不上报为连败，但必须留痕（静默失败无从排查）
            logger.warning("整合编辑未通过校验，整批不写: %s", e)
            raise
        except Exception as e:
            self._record_failure(f"LLM 抽取编辑指令失败: {e!r}")
            return

        # 阶段 2：逐条应用。单条失败只跳过该条，不让它带走同批其余编辑。
        applied, not_found, failures = self._apply_batch(batch, refs)

        # 定位失败没有副作用：给一次修复轮，用最新快照的编号改正
        if not_found:
            repaired, repair_failures = await self._repair(new_msgs, applied, not_found)
            applied += repaired
            failures += repair_failures

        # 阶段 3：结算——条目被取代/删除后空掉的分册整块删掉，让「全量喂旧
        # 记忆」的总量有界（记忆的语义是当前有效知识，历史交给 Recall）。
        # 结算失败只记日志：它不是编辑层面的失败，不参与下面「这批消息有没有被消费」的判定。
        try:
            self._cleanup_empty_shards()
        except Exception as e:
            logger.warning("空分册清理失败: %s", e)

        # 若 block_manager 支持 git，则提交变更
        if hasattr(self.block_manager, '_commit') and callable(self.block_manager._commit):
            self.block_manager._commit(f"consolidation: {len(new_msgs)} 条消息")

        if failures and applied:
            # 已有编辑落盘：这批消息已被消费，**不再重放**（重放同一批编辑会在 add 上
            # 产生重复行）。失败如实写日志，游标照常推进。
            logger.warning("整合部分失败，跳过 %d 条：%s", len(failures), "；".join(failures))

        if not applied and (failures or not_found):
            # 一条都没写成功：这批消息还没被消费，保留游标下轮重试（连败达阈值才放弃）
            reasons = failures or [_describe_edit(edit) for edit in not_found]
            self._record_failure(f"整合未落地任何编辑: {'；'.join(reasons)}")
            return

        # 推进游标到当前总行数，并重置失败计数
        self._cursor = self.message_manager.size(self.agent_state.agent_id)
        self._failures = 0

    async def _extract_batch(self, prompt: str) -> MemoryEditBatch:
        """调模型抽取一批编辑指令，并做阶段 1 的全量预验证。

        Args:
            prompt: str，本次整合的提示（首轮用 _build_prompt 的原稿，修复轮带补充说明）。

        Returns:
            MemoryEditBatch，通过校验的指令批次；空批次即 NOOP。

        Raises:
            MemoryEditValidationError: 任一条编辑未通过校验（调用方据此整批不写）。
        """
        batch = await self.structured.extract(
            prompt=prompt, schema=MemoryEditBatch,
            fallback=lambda: MemoryEditBatch(edits=[]))
        for edit in batch.edits:
            self._validate_edit(edit)
        return batch

    def _record_failure(self, reason: str) -> None:
        """记一次**未落盘任何编辑**的整批失败：日志 + 连败计数；达阈值强制推进游标。

        只在「一条编辑都没写进块」时调用——此时重试是安全的，所以保留游标让下一轮
        重试，连败达阈值才放弃（防死锁：同一批坏编辑反复失败会把管道卡住）。已经
        落地过编辑的批次不走这里：那批消息已经消费掉，重放会产生重复写入。

        Args:
            reason: str，失败原因（写进日志，便于定位是模型输出还是落盘环节的问题）。
        """
        self._failures += 1
        logger.warning("整合失败（连败第 %d 次）: %s", self._failures, reason)
        if self._failures >= _MAX_CONSECUTIVE_FAILURES:
            # 同一批坏编辑反复失败：不推进的话每个 REPL 轮次都会重试，管道被卡住。
            # 计数归零：放弃的这一批到此为止，下一批内容应当重新获得完整的重试额度。
            logger.warning("整合连续失败 %d 次，跳过这批消息推进游标",
                           self._failures)
            self._cursor = self.message_manager.size(self.agent_state.agent_id)
            self._failures = 0

    def _existing_memory(self) -> list:
        """收集当前可写块的快照，供 prompt 呈现旧记忆。

        Returns:
            list[Block]，可写块（两个核心块 + 三类前缀家族的日期分册），按 label 排序。
        """
        blocks = [b for b in self.block_manager.list_blocks()
                  if _is_writable_label(b.label)]
        return sorted(blocks, key=lambda b: b.label or "")

    def _render_existing(self) -> tuple[list[str], dict[int, "_LineRef"]]:
        """把可写块的当前内容渲染成带编号的清单，并同步建立编号 → 行引用映射。

        编号是跨分册家族的连续流水号：同一类型的条目可能散在多册里，模型只回填一个
        整数就能唯一定位，不必抄正文、也不必碰分册名与日期。编号与原文必须在**同一趟
        遍历**里产生——两处各算一次，任何一处改动都会让定位静默错位。

        Returns:
            tuple[list[str], dict[int, _LineRef]]，提示片段与编号到行引用的映射
            （全部块为空时映射为空）。
        """
        parts: list[str] = []
        refs: dict[int, _LineRef] = {}
        n = 0
        for block in self._existing_memory():
            desc = f" — {block.description}" if block.description else ""
            parts.append(f"## {block.label}{desc}（{len(block.value)} 字）")
            lines = [ln for ln in block.value.splitlines() if ln.strip()]
            if not lines:
                parts.append("（空）")
                continue
            target = _target_of(block.label or "")
            for line in lines:
                n += 1
                refs[n] = _LineRef(target=target, label=block.label or "", text=line)
                parts.append(f"[{n}] {line}")
        return parts, refs

    def _build_prompt(self, new_msgs: list,
                      note: str = "") -> tuple[str, dict[int, "_LineRef"]]:
        """构造整合指令生成提示：目标与动作声明 + 带编号的旧记忆 + 本轮对话。

        **旧记忆是消解矛盾的前提**：把全部可写块的当前内容摊开，模型才能看出
        新信息推翻了哪一条旧条目、哪几条是重复的。提示里的目标类型与动作说明
        与 _validate_edit 的校验面一一对应。

        Args:
            new_msgs: 本轮新增的消息列表（已按时间升序）。
            note: 追加在提示末尾的补充说明（修复轮用它列出已写入与定位失败的条目）。

        Returns:
            tuple[str, dict[int, _LineRef]]，提示文本与本次渲染的编号映射——两者必须
            成对使用，应用编辑时的行号只在这次渲染里有效。
        """
        parts = [
            "你是 BioPilot 的记忆整合器（consolidation）。分析本轮对话，输出记忆编辑指令。",
            "目标 target（只能写这些类型；块的日期分册由系统拼装，你不要写日期）：",
            "- profile — 用户身份/研究方向/偏好/背景",
            "- assistant — 助手角色/工作方式认知变化",
            "- feedback — 用户对做法的反馈与纠正",
            "- project — 研究项目/论文进展的关键事实",
            "- reference — 文献/资料可长期复用的要点",
            "动作 action：",
            "- add — 新增一行，content 给这一行的文字",
            "- supersede — line 给旧行行首的 [编号]（如 [7] 就写 7），把那一行换成 content（新的一行）",
            "- drop — line 给旧行行首的 [编号]，删掉那一行（结论作废）",
            "- rewrite — 整块重写，content 给完整新内容；只允许 target=profile / assistant",
            "规则：值得长期记住才写；**没有值得沉淀的内容就返回空 edits（不写任何块，这是正常的）**；"
            "旧结论被推翻时用 supersede 换掉旧行，不要写出一条互相矛盾的新条目；"
            "supersede/drop 的 line 必须是「已有记忆」里某一行行首的编号，不要自己数、也不要编造；"
            "一条指令只动一行，要删多行就发多条 drop；"
            "单批最多 20 条；每条内容一行、自带主语，不写日期（日期由系统加）。",
            "", "已有记忆（每行行首的 [n] 是定位编号；这些是各块的当前内容——判断重复与矛盾必须对照它们）：",
        ]
        existing_parts, refs = self._render_existing()
        parts.extend(existing_parts)
        parts.append("")
        parts.append("本轮对话：")
        # 将每条消息的 role 和 content 以文本形式拼入
        for m in new_msgs:
            parts.append(f"[{m.role.value}] {m.content}")
        if note:
            parts.append("")
            parts.append(note)
        return "\n".join(parts), refs

    def _validate_edit(self, edit: MemoryEdit) -> None:
        """阶段 1 校验：动作与目标是否匹配、必要字段是否齐全。

        LLM 输出不可信，写入前必须把语义约束查一遍：整块重写只允许两个核心块
        （前缀分册是条目流，整块重写会抹掉分册里的其他条目）；supersede/drop
        必须给 line（编号是唯一能定位旧行的依据）；add/supersede/rewrite 必须给
        content。target 与 action 的取值面由 pydantic 的 Literal 在构造期锁定，
        编号是否存在要等渲染快照才能判断，留给 _resolve。

        Args:
            edit: MemoryEdit，待校验的编辑指令。

        Raises:
            MemoryEditValidationError: 动作与目标不匹配、或必要字段为空/非法。
        """
        if edit.action == "rewrite" and edit.target in _PREFIX_TARGETS:
            raise MemoryEditValidationError(
                f"整块重写只允许 profile/assistant，不能用于 {edit.target}")
        if edit.action in ("supersede", "drop"):
            if edit.line is None:
                raise MemoryEditValidationError(f"{edit.action} 需要 line（旧行行首的编号）")
            if edit.line < 1:
                raise MemoryEditValidationError(f"{edit.action} 的 line 必须≥1，收到 {edit.line}")
        if edit.action != "drop" and not edit.content.strip():
            raise MemoryEditValidationError(f"{edit.action} 需要 content")

    def _label_for(self, target: str) -> str:
        """目标类型 → 块 label（前缀家族按当天日期分册，核心块用原 label）。

        Args:
            target: str，目标类型（profile/assistant/feedback/project/reference）。

        Returns:
            str，块 label，形如 `<类型>_<YYYY-MM-DD>` 或 `profile`。
        """
        if target in _PREFIX_TARGETS:
            return f"{target}_{_today()}"
        return target

    def _apply_batch(self, batch: MemoryEditBatch,
                     refs: dict[int, "_LineRef"]) -> tuple[list[MemoryEdit],
                                                           list[MemoryEdit], list[str]]:
        """逐条应用一批编辑，单条失败只影响该条。

        Args:
            batch: MemoryEditBatch，已通过阶段 1 校验的指令批次。
            refs: dict[int, _LineRef]，渲染提示时建立的编号映射。

        Returns:
            tuple[list[MemoryEdit], list[MemoryEdit], list[str]]，分别是已落地的
            指令、定位失败（可修复）的指令与其它失败（已跳过）的描述。
        """
        applied: list[MemoryEdit] = []
        not_found: list[MemoryEdit] = []
        failures: list[str] = []
        for edit in batch.edits:
            try:
                self._apply_edit(edit, refs)
            except MemoryEditTargetNotFound:
                not_found.append(edit)
                logger.warning("整合编辑定位失败（待修复）: %s", _describe_edit(edit))
            except Exception as e:
                failures.append(f"{edit.target}/{edit.action}: {e}")
                logger.warning("整合编辑应用失败（已跳过该条）: target=%s action=%s err=%s",
                               edit.target, edit.action, e)
            else:
                applied.append(edit)
        return applied, not_found, failures

    async def _repair(self, new_msgs: list, applied: list[MemoryEdit],
                      not_found: list[MemoryEdit]) -> tuple[list[MemoryEdit], list[str]]:
        """定位失败后补跑一轮：用重新渲染的最新编号让模型改正，只此一次。

        修复轮能看到已经写入的条目（避免重复 add）与没能定位的条目（重新给编号）。
        它自身不再递归修复：已经给过正确编号仍改不过来，说明模型输出不可信，继续
        重试只会烧调用。

        Args:
            new_msgs: 本轮新增消息（修复轮仍需同样的对话上下文）。
            applied: list[MemoryEdit]，上一批已落地的指令。
            not_found: list[MemoryEdit]，上一批定位失败的指令。

        Returns:
            tuple[list[MemoryEdit], list[str]]，修复轮落地的指令与其它失败（已跳过）
            的描述。
        """
        prompt, refs = self._build_prompt(
            new_msgs, note=self._repair_note(applied, not_found))
        try:
            batch = await self._extract_batch(prompt)
        except MemoryEditValidationError as e:
            logger.warning("整合修复轮输出未通过校验，放弃修复: %s", e)
            return [], []
        except Exception as e:
            logger.warning("整合修复轮抽取失败: %r", e)
            return [], []

        # 修复轮里可能又带上一批原样返回的指令：已落地的跳过，避免 add 被写两次
        done = {_edit_key(edit) for edit in applied}
        retry = [edit for edit in batch.edits if _edit_key(edit) not in done]
        if len(retry) < len(batch.edits):
            logger.warning("修复轮跳过 %d 条已落地的重复指令", len(batch.edits) - len(retry))

        repaired, still_missing, failures = self._apply_batch(
            MemoryEditBatch(edits=retry), refs)
        if still_missing:
            logger.warning("整合修复后仍无法定位 %d 条：%s",
                           len(still_missing), "；".join(_describe_edit(e) for e in still_missing))
        return repaired, failures

    @staticmethod
    def _repair_note(applied: list[MemoryEdit], not_found: list[MemoryEdit]) -> str:
        """拼出修复轮的补充说明（已写入清单 + 定位失败清单 + 只补发的要求）。

        Args:
            applied: list[MemoryEdit]，已落地的指令。
            not_found: list[MemoryEdit]，定位失败的指令。

        Returns:
            str，追加在提示末尾的说明文本。
        """
        lines = [
            "这是修复轮：上一批指令里有几条没能在「已有记忆」里定位到旧行。",
            "下面这些已经写入成功，不要再重复提交：",
        ]
        if applied:
            lines.extend(f"- {_describe_edit(edit)}" for edit in applied)
        else:
            lines.append("- （无）")
        lines.append("下面这些没有定位到。括号里的编号是**你上一批给出的编号**，"
                     "不是当前编号——请以上面「已有记忆」里的最新编号为准：")
        lines.extend(f"- {_describe_edit(edit)}" for edit in not_found)
        lines.append("请按上面「已有记忆」的最新编号只补发需要纠正的编辑；不需要补发就返回空 edits。")
        return "\n".join(lines)

    def _resolve(self, edit: MemoryEdit, refs: dict[int, "_LineRef"]) -> _LineRef:
        """把指令里的编号解析成快照里的行（编号必须在本次渲染的映射里）。

        Args:
            edit: MemoryEdit，action 为 supersede / drop 的指令。
            refs: dict[int, _LineRef]，本次渲染建立的编号映射。

        Returns:
            _LineRef，该编号对应的行引用。

        Raises:
            MemoryEditTargetNotFound: 编号不存在，或该编号属于另一类目标。
        """
        ref = refs.get(edit.line) if edit.line is not None else None
        if ref is None or ref.target != edit.target:
            raise MemoryEditTargetNotFound(edit.target, edit.line)
        return ref

    def _apply_edit(self, edit: MemoryEdit, refs: dict[int, "_LineRef"]) -> None:
        """把行级编辑落到目标块（前缀家族写满自动续号）。

        add 追加一行；supersede 删掉编号命中的旧行再追加新行；drop 只删；
        rewrite 整块替换（仅核心块）。行级操作都在 mutate_block 里完成——整段
        读-算-写在一次持锁内，并发写不会互相抹掉。

        Args:
            edit: MemoryEdit，已通过校验的编辑指令。
            refs: dict[int, _LineRef]，渲染提示时建立的编号映射（应用期不重算行号）。

        Raises:
            MemoryEditTargetNotFound: supersede/drop 的编号定位不到旧行，或承载它的块已消失。
            BlockLimitExceeded: 核心块写满（分册会续号，只有核心块上抛）。
        """
        if edit.action == "rewrite":
            try:
                self.block_manager.mutate_block(edit.target, lambda v: edit.content)
            except KeyError:
                self.block_manager.create_block(edit.target, edit.content)
            return
        if edit.action == "add":
            self._add_line(edit.target, edit.content.strip())
            return
        self._replace_or_drop(edit, self._resolve(edit, refs))

    def _add_line(self, target: str, line: str) -> None:
        """把一行加进该类型当天的分册；写满则续号到下一册（确定性，不丢数据）。

        块不存在时直接建块写入，已存在则原子追加；撞上字符上限就换下一册再试。
        核心块不参与分册——写满如实上抛，由整块重写收敛。

        Args:
            target: str，目标类型。
            line: str，已去空白的条目行。

        Raises:
            BlockLimitExceeded: 非分册目标（profile/assistant）写满。
        """
        base = self._label_for(target)
        shardable = target in _PREFIX_TARGETS
        n = 1
        while True:
            label = base if n == 1 else f"{base}_{n}"
            if self.block_manager.get_block_by_label(label) is None:
                self.block_manager.create_block(label, line)
                return
            try:
                self.block_manager.mutate_block(
                    label, lambda v: f"{v.strip()}\n{line}" if v.strip() else line)
                return
            except BlockLimitExceeded:
                if not shardable:
                    raise
                n += 1          # 这一册写满：续号换下一册

    def _replace_or_drop(self, edit: MemoryEdit, ref: _LineRef) -> None:
        """按快照里的整行原文定位并处理（supersede 顺带补上新行）。

        定位依据是原文而非下标：提示生成之后块可能被其他写者改过，原文对不上就
        说明这一行已经不在了——如实报错让修复轮重来，绝不挪到别的行上动手。只删
        命中那**一行**：内容完全相同的重复条目有多行时，别的行各自有自己的编号，
        不在这一次编辑的范围内。

        Args:
            edit: MemoryEdit，action 为 supersede / drop 的指令。
            ref: _LineRef，本次快照里该编号对应的行。

        Raises:
            MemoryEditTargetNotFound: 块里已经没有这一行原文，或承载它的块已被删除。
        """
        def _mutate(v: str) -> str | None:
            lines = [ln for ln in v.splitlines() if ln.strip()]
            kept: list[str] = []
            removed = False
            for line in lines:
                if not removed and line == ref.text:
                    removed = True          # 只删第一处命中，其余同文行保持原编号
                    continue
                kept.append(line)
            if not removed:
                return None
            if edit.action == "supersede":
                kept.append(edit.content.strip())
            return "\n".join(kept)

        try:
            block = self.block_manager.mutate_block(ref.label, _mutate)
        except KeyError:
            # 快照之后分册被别的写者删掉：同样是无副作用的定位失败，交给修复轮
            raise MemoryEditTargetNotFound(edit.target, edit.line) from None
        if block is None:
            raise MemoryEditTargetNotFound(edit.target, edit.line)

    def _cleanup_empty_shards(self) -> list[str]:
        """删掉已经空掉的条目分册（取代/删除留下的空壳）。

        记忆的语义是「当前有效的知识」：条目被取代或删除后，承载它的分册若已空就
        整块删掉——否则分册只增不减，逐轮把全部旧记忆喂进 prompt 会越来越肥。
        核心块不在此列（它们常驻，靠整块重写收敛）。

        Returns:
            list[str]，被删除的块 label（无删除时为空）。
        """
        removed: list[str] = []
        for block in self.block_manager.list_blocks():
            label = block.label or ""
            if label.startswith(_WRITABLE_PREFIXES) and not block.value.strip():
                self.block_manager.delete_block(block.id)
                removed.append(label)
        return removed
