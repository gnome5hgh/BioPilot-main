"""意图类别：11 值，类别词汇的唯一声明点。

类别回答的是「用户要哪一类工作」，按**产物主人**划分——一个类别对应一类产物/事务
的责任人，而不是一个具体动作。枚举值即类别名，与知识库
`biopilot/engine/intent/data/taxonomy.yaml` 的键逐项一致（装载期 fail-closed 校验，
见 `taxonomy.py`）。

**领域意图与领域 agent 一一对应**：`paper` / `note` / `research` / `bioinformatics` /
`index` 分别对应 paper-agent / note-agent / research-agent / bio-agent / rag-agent。
这张对应关系是责任归属，不是运行时路由——派发仍由 supervisor 按能力自主决定，
`spawn.py` 对意图零引用。
"""
from enum import StrEnum

__all__ = ["IntentType"]


class IntentType(StrEnum):
    """11 个意图类别。

    **不按「派发 / 不派发」分组**：每个类别就是「用户要哪一类工作」，值即类别名。
    值得单列的区别要两条同时成立：**supervisor 的动作确实不同**，且**这个区别从
    用户原句里读不出来**。凡是能从文本读出的动作（读/写/删/查）与类别正交，单列
    只会制造误差——三个删除类因此并入了各自的领域类别。
    """

    # ── 业务：前五个各对应一个可派发的领域责任人 ──
    PAPER = "paper"                          # 论文事务：检索/下载/读指定论文/分析图表
    NOTE = "note"                            # 笔记事务：撰写/修订/删除笔记
    RESEARCH = "research"                    # 选题事务：选题发现/研究计划/删选题产物
    BIOINFORMATICS = "bioinformatics"        # 生信分析与数据执行：统计/差异/富集/单细胞/沙箱执行
    INDEX = "index"                          # 语料索引体检：状态/进度/失败原因
    MEMORY = "memory"                        # 长期记忆查询；**用户陈述自身信息**也归此类
    QUESTION = "question"                    # 即问即答：先自答，需依据时取材料

    # ── 系统：不派发领域角色（feedback 由后台整合沉淀）──
    CHITCHAT = "chitchat"                    # 寒暄应答
    OUT_OF_SCOPE = "out_of_scope"            # 非本系统任务：明确越界，或看不出要做什么
    HELP = "help"                            # 功能询问与网页端平台操作指引
    FEEDBACK = "feedback"                    # 对系统表现的评价与纠正
