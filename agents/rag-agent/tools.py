"""rag-agent 的工具装配：平台论文检索 + 索引体检（RAG 一域的全部工具）。

- **检索** `rag_retrieve`：按 query 取回命中片段（含来源、路径与摘录）。这是「在语料里
  找材料」的唯一入口——其他角色要检索就派发本角色，一次派发可带多个检索式
  （本角色逐个调用工具，不为每个 query 各回一轮）。
- **看图** `view_image`：按检索结果里的「图片对象键」把图表**原图**取回来交给模型看。
  媒体块的摘录是空的（内容在图里），所以「检索到表/图 → 想弄清它画了什么」这一步
  由本工具收口，不必跨角色派发。
- **体检** `index_status`：只读对照索引状态 / 向量库 / 关键词索引，报告已索引多少、
  配方是否一致、PDF 解析器分布。诊断权也在责任人手里——「索引好像不对」先跑它。

索引写入（勾选/重试/全部重新索引）由 Java 平台状态驱动，本角色不再做目录扫描，
也不提供 `index_paths` / `reindex_all`。不给文件读写工具、不给 glob/grep。
失败如实回报，是否请示用户由上级决定。也不装记忆工具：
检索与索引维护不产生需要沉淀的清单或历史。
"""
from biopilot.config import BioPilotConfig
from biopilot.tools.services.assembly import make_tools
from biopilot.tools.rag import IndexStatusTool, RagRetrieveTool, ViewImageTool
from biopilot.tools.recall import get_recall_tools

# config 在 import 时构造（每进程静态、无副作用，对齐 make_tools 惯例）
TOOLS = make_tools(BioPilotConfig.from_env(), [
    RagRetrieveTool, ViewImageTool, IndexStatusTool,
]) + get_recall_tools()
