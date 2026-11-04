"""RAG 域的跨文件共享常量：块 id 长度、块类型词汇与平台论文的文档标识。

只收**跨文件共享、且不属于某一个消费方**的常量。块 id 长度是切块方与索引方共同的
结构契约——chunker 按它生成块 id，indexer 按同一规则生成媒体块的 id，改任一处都会
让两边对不上。块类型词汇是一套取值：chunker 给正文块打默认值、indexer 给图/表块打
类型、vector_store 反序列化时补默认值，三处必须是同一套词。平台论文的文档标识由
索引器与平台适配层共同拼装/解析，也放这里。正则、提示词、退避基数、容量阈值这类
只服务单一消费方的结构常量留在消费处就地声明。
"""

__all__ = ["CHUNK_ID_LEN", "CHUNK_TYPE_FIGURE", "CHUNK_TYPE_TABLE", "CHUNK_TYPE_TEXT",
           "PAPER_DOC_PREFIX", "paper_doc_key", "paper_id_of"]

#: 块 id 的哈希前缀长度（字符）：块 id 取 ``sha1(绝对路径:序号)`` 十六进制串的
#: 前 N 个字符。结构契约——改它所有块 id 变化，必须全量重建索引，否则旧块残留、
#: 新块 id 对不上（indexer 的「先删后建」依赖 id 稳定，与 chunker 共用同一规则）。
CHUNK_ID_LEN = 16

#: 块类型取值：普通正文块 / 表格块 / 插图块。媒体块（表、图）的正文是区域内
#: 文字、字幕字段另存注文原文，两者在检索结果里分开呈现。
CHUNK_TYPE_TEXT = "text"
CHUNK_TYPE_TABLE = "table"
CHUNK_TYPE_FIGURE = "figure"

#: 平台论文的文档标识前缀：知识库论文没有本地文件，用 ``paper:<paper_id>`` 作
#: 文档身份（块 id、Chunk.path、向量库 path 字段、索引状态键都用它）。索引器与
#: 平台适配层共同消费这套规则，两边必须用同一份拼接/解析实现。
PAPER_DOC_PREFIX = "paper:"


def paper_doc_key(paper_id: str) -> str:
    """把平台论文 id 转成索引里的文档标识。

    Args:
        paper_id: 平台论文 id。

    Returns:
        str: ``paper:<id>``。
    """
    return f"{PAPER_DOC_PREFIX}{str(paper_id).strip()}"


def paper_id_of(doc_key: str) -> str | None:
    """从文档标识里取出平台论文 id。

    本地语料文档的标识是绝对路径，取不出论文 id 时返回 None——调用方据此区分
    「平台论文」与「本地文件」，而不是靠路径形态猜。

    Args:
        doc_key: ``Chunk.path`` 或索引状态里的文档标识。

    Returns:
        str | None: 论文 id；不是平台论文时返回 None。
    """
    key = str(doc_key or "")
    if not key.startswith(PAPER_DOC_PREFIX):
        return None
    return key[len(PAPER_DOC_PREFIX):] or None
