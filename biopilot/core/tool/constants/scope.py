"""产物语义根名的词表。

`_root_map`（语义根名 → 绝对路径）的键，也是工具 `root_hints` 唯一合法的取值：
写成别的字面量不会报错，只会让 description 里的 `[目录]` 提示行**静默消失**
（`make_tools` 遇到不认识的名字直接跳过），模型于是看不到产物位置。

笔记与论文不再有本地语义根：笔记定稿进文档编辑器，论文由平台 OSS 提供字节。
"""

from enum import StrEnum

__all__ = ["ScopeRoot", "WRITE_HINTS", "READ_HINTS", "SEARCH_HINTS"]


class ScopeRoot(StrEnum):
    """工具的语义根名。"""

    #: 选题与研究计划根
    RESEARCH = "research"
    #: 记忆数据根（blocks 库所在）
    MEMORY = "memory"
    #: 分析产物根（生信分析代码与结果落点）
    ANALYSIS = "analysis"
    #: 草稿根（路径对模型不透明，故 `[目录]` 提示会跳过它）
    SCRATCH = "scratch"


#: 写类工具（write/edit）的提示根：写记忆、写选题产物、写分析结果
WRITE_HINTS = [ScopeRoot.MEMORY, ScopeRoot.RESEARCH, ScopeRoot.ANALYSIS]

#: 检索类只读工具（glob/grep）的提示根：在记忆与产物里找东西
SEARCH_HINTS = [ScopeRoot.MEMORY, ScopeRoot.RESEARCH, ScopeRoot.ANALYSIS]

#: 全文读工具的提示根：多一个 scratch（草稿也要能读回）
READ_HINTS = [
    ScopeRoot.MEMORY,
    ScopeRoot.SCRATCH,
    ScopeRoot.RESEARCH,
    ScopeRoot.ANALYSIS,
]
