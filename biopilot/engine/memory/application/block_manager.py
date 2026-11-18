"""记忆块服务：块 CRUD + 写前快照 + 并发保护。

长期记忆的写入统一由后台整合（`MemoryConsolidator`）完成，任何 agent 都不持有
写工具；本模块是它唯一的写入口。更新块前把旧值整体快照进 block_history、版本号
+1；写入走 CAS（带期望版本的条件更新），版本被并发推进时拒绝而非静默覆盖。
读-改-写类操作（追加/替换/删除行）必须走 `mutate_block`——它把整段序列放进一次
持锁事务，避免两个并发写者各自基于同一份旧值计算后互相抹掉。

本类只依赖 ``BlockRepository`` 端口（MySQL 实现在 adapters），业务不变式
（read_only / limit / 纯函数重放）全部在这里持有。
"""
from __future__ import annotations

import logging
from typing import Callable

from biopilot.engine.memory.constants import DEFAULT_ASSISTANT, DEFAULT_PROFILE
from biopilot.engine.memory.domain.errors import BlockLimitExceeded, ConcurrentUpdateError
from biopilot.engine.memory.domain.ports import BlockRepository
from biopilot.engine.memory.domain.schemas.block import Block

__all__ = ["BlockManager"]

logger = logging.getLogger(__name__)

_READ_ONLY = "block is read-only"

#: 旧核心块 label → 新 label（一次性迁移映射：human/persona 收敛为 profile/assistant）
_LEGACY_LABELS = {"human": "profile", "persona": "assistant"}

#: 已下线功能的块 label：启动时一次性清除（幂等）。这些块的写入者已退役，
#: 留着既没有读者、又会误导模型。
_REMOVED_BLOCKS = ("history_list", "unread_list")


class BlockManager:
    """核心块业务层：持有 read_only / limit 不变式，维护写前快照历史链。

    Attributes:
        blocks: BlockRepository，块与历史快照的存储端口
        user_id: 归属用户（行级隔离键）
    """

    def __init__(self, blocks: BlockRepository, user_id: str):
        """初始化块管理器（用户域实例：本实例所有块读写都限定在该用户名下）。

        Args:
            blocks: 块存储端口（MySqlBlockRepository 或测试假件）。
            user_id: 归属用户（行级隔离键，必填）。装配层传网关携带的 user_id
                （信任边界：内网带入即真相）。

        Raises:
            ValueError: user_id 缺失或为空——多用户隔离的键不允许缺省。
        """
        if not user_id:
            raise ValueError("BlockManager 需要 user_id（多用户行级隔离的键，缺省即拒绝）")
        self.blocks = blocks
        self.user_id = user_id

    def _invariants(self, block: Block, new_value: str | None) -> str | None:
        """写前业务校验：read_only 拒写、limit 超限拒绝。

        Args:
            block: 当前块（含 read_only 与 limit）。
            new_value: mutator 算出的新值；None 表示「判定不改」，直接放行。

        Returns:
            new_value 原样（校验通过）。

        Raises:
            ValueError: 块为 read_only。
            BlockLimitExceeded: 新值超过块上限。
        """
        if new_value is None:
            return None
        if block.read_only:
            raise ValueError(_READ_ONLY)
        if len(new_value) > block.limit:
            raise BlockLimitExceeded(block.label, block.limit)
        return new_value

    def _db_history(self, label: str) -> list[dict]:
        """测试辅助：按 label 取该块的历史快照。

        Args:
            label: 块的标签名称。

        Returns:
            该块的历史快照列表（bio_memory_block_history 表行），若块不存在返回空列表。
        """
        block = self.blocks.get_by_label(label)
        if block is None:
            return []
        return self.blocks.history(block.id)

    def create_block(self, label: str, value: str, limit: int = 2000,
                     description: str | None = None,
                     read_only: bool = False) -> Block:
        """新建块并落盘（初始版本号 1）。

        Args:
            label: 块的标签（唯一标识符，如 "assistant", "profile"）。
            value: 块的内容文本。
            limit: 字符上限（默认 2000），更新时若超过将拒绝。
            description: 块的描述（可选，用于展示）。
            read_only: 是否为只读块（只读块不可更新/删除，默认 False）。

        Returns:
            新创建的 Block 实例（含自动生成的 id 和初始 version=1）。
        """
        b = Block.new(label, value)
        b.limit = limit
        b.description = description
        b.read_only = read_only
        self.blocks.create(b)
        return b

    def get_block(self, block_id: str) -> Block:
        """按 id 取块；不存在抛 KeyError（变异工具硬失败的来源）。

        Args:
            block_id: 块的唯一标识。

        Returns:
            块对象。

        Raises:
            KeyError: 当 block_id 不存在时。
        """
        block = self.blocks.get_by_id(block_id)
        if block is None:
            raise KeyError(f"block {block_id} not found")
        return block

    def get_block_by_label(self, label: str) -> Block | None:
        """按 label 取块；不存在返回 None（工具层据此判断「该建还是该报错」）。

        Args:
            label: 块的标签名称。

        Returns:
            块对象或 None。
        """
        return self.blocks.get_by_label(label)

    def get_block_history(self, block_id: str) -> list[dict]:
        """按块 id 返回其全部历史快照（从旧到新，即 bio_memory_block_history 表行）。

        Args:
            block_id: 块的唯一标识。

        Returns:
            该块的历史快照列表（含 version/value 等列）；无历史时为空列表。
        """
        return self.blocks.history(block_id)

    def migrate_legacy_labels(self) -> list[str]:
        """把旧核心块 label（human/persona）迁移为 profile/assistant（幂等）。

        在 ensure_default_blocks 之前调用：先迁移再播种，保证旧库不会因
        「新 label 缺失」而被播种出第二套并存块。value/id/创建时间原样保留。

        Returns:
            实际迁移到的新 label 列表（无迁移时为空）。
        """
        migrated: list[str] = []
        for old, new in _LEGACY_LABELS.items():
            old_block = self.get_block_by_label(old)
            if old_block is None:
                continue
            if self.get_block_by_label(new) is not None:
                logger.warning("label 迁移跳过：%s 与 %s 并存，请人工处理", old, new)
                continue
            self.blocks.update_label(old_block.id, new)
            migrated.append(new)
        return migrated

    def ensure_default_blocks(self) -> list[str]:
        """播种默认核心记忆块：assistant/profile 各自缺失才创建，绝不覆盖已有块。

        Returns:
            实际创建的 label 列表（无创建时为空）。

        设计意图：
            - assistant 是助手自我认知/工作方式记忆、profile 是用户画像引导占位
              ——两者是 Memory.compile() 每轮渲染的 system/ 块，缺失时记忆系统呈空壳。
            - 幂等性：已存在的块（含用户经 self-editing 改过的）不动，避免意外覆盖。
        """
        created: list[str] = []
        for label, value in (("assistant", DEFAULT_ASSISTANT),
                             ("profile", DEFAULT_PROFILE)):
            if self.get_block_by_label(label) is None:
                self.create_block(label, value)
                created.append(label)
        return created

    def purge_removed_blocks(self) -> list[str]:
        """删除已下线功能的块（幂等）：这些块的写入者已退役，留着只会误导模型。

        Returns:
            实际删除的 label 列表（无删除时为空）。
        """
        removed: list[str] = []
        for label in _REMOVED_BLOCKS:
            block = self.get_block_by_label(label)
            if block is None:
                continue
            self.delete_block(block.id)
            removed.append(label)
        return removed

    def list_blocks(self) -> list[Block]:
        """返回全部块（按创建时间排序），供 Memory 重建与 head 编译。

        Returns:
            所有块的列表（按 DB 插入顺序，即创建时间升序）。
        """
        return self.blocks.list_blocks()

    def update_block_value(self, label: str, value: str) -> Block:
        """把块值整体设为 value（原子：读取、快照、写入在一次持锁内完成）。

        Args:
            label: 块的标签。
            value: 新的内容文本。

        Returns:
            更新后的 Block 对象（含新的 version）。

        Raises:
            KeyError: label 不存在。
            BlockLimitExceeded: 新 value 超过块上限。
            ConcurrentUpdateError: 读取后写入前版本被其他写者推进（CAS 拒绝）。
        """
        def _set(block: Block) -> str:
            self._invariants(block, value)
            return value

        return self.blocks.mutate(label, _set)

    def mutate_block(self, label: str,
                     mutate: Callable[[str], str | None]) -> Block | None:
        """原子读-改-写：读当前值 → 交给 mutate 计算新值 → 写回，整段一次持锁。

        追加/替换类操作必须走这里：它们的「读旧值 → 算新值 → 写」跨多次调用，分开
        执行时两个并发写者会各自基于同一份旧值计算，后写者把前者的改动抹掉。

        Args:
            label: 目标块标签。
            mutate: 接收当前块值、返回新值的纯函数。返回 None 表示「判定不改」——
                不写、不推进版本，直接返回 None（调用方据此回报未命中，如替换锚点
                不存在）。必须是旧值的纯函数（只依赖入参），CAS 冲突后会在最新值上
                重放它；依赖外部读到的状态会让重放失真。

        Returns:
            更新后的 Block；mutate 返回 None 时为 None。

        Raises:
            KeyError: label 不存在。
            BlockLimitExceeded: 新值超过块上限（含 mutator 抛出的校验错误）。
            ConcurrentUpdateError: 连续重试仍冲突（说明有绕过本入口的写者）。
        """
        def _runner(block: Block) -> str | None:
            if block.read_only:
                raise ValueError(_READ_ONLY)
            return self._invariants(block, mutate(block.value))

        return self.blocks.mutate(label, _runner)

    def delete_block(self, block_id: str) -> None:
        """删除块。read_only 块拒绝（与 update_block_value 一致），防误删保护块。

        Args:
            block_id: 块的唯一标识。

        Raises:
            KeyError: block_id 不存在。
            ValueError: 块为 read_only。
        """
        block = self.blocks.get_by_id(block_id)
        if block is None:
            raise KeyError(f"block {block_id} not found")
        if block.read_only:
            raise ValueError(_READ_ONLY)
        self.blocks.delete(block_id)

    def checkpoint_block(self, block_id: str) -> None:
        """手动快照：把当前块状态写进 bio_memory_block_history（version 记为 0，表示非更新前快照）。

        Args:
            block_id: 块的唯一标识。

        用途：允许在未发生更新的情况下手动保存一个检查点，例如在重大操作前备份。
        version=0 用于区分「手动检查点」和「更新前自动快照」（更新前快照的 version 为旧版本号）。
        """
        b = self.get_block(block_id)
        self.blocks.checkpoint(b, version=0)

    def restore_block(self, block_history_id: int) -> Block:
        """按历史快照回滚块：把快照的值写回 bio_memory_block 行，返回回滚后的块。

        Args:
            block_history_id: bio_memory_block_history 表的自增主键 ID。

        Returns:
            回滚后的 Block 对象。

        Raises:
            KeyError: 快照不存在，或其对应块行已被删除。

        回滚逻辑：
            - 从 bio_memory_block_history 读取快照数据（包含 block_id, value）。
            - 以「当前行版本」为 CAS 期望版本，把快照值写回 bio_memory_block 行：写入成功后
              版本推进为当前版本 + 1（回滚也照常推进版本，不做版本回退）。快照里的
              version 是历史写入时的标注，不能当 CAS 期望值。
            - 注意：回滚不会生成新的历史记录（不记录“回滚操作”本身），
              如需可撤销的回滚，调用方可在回滚后手动调用 checkpoint_block。
        """
        snap = self.blocks.restore_snapshot(block_history_id)
        cur = self.blocks.get_by_id(snap["block_id"])
        if cur is None:
            # 块行已删、只剩历史快照：报「块不存在」，与 get_block 的失败语义一致。
            raise KeyError(f"block {snap['block_id']} not found")
        self.blocks.update_value(snap["block_id"], snap["value"],
                                 expected_version=cur.version)
        return self.get_block(snap["block_id"])
