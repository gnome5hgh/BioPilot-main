"""IndexStatusTool：平台论文索引体检——对照索引状态、向量库与关键词索引。

索引器（rag-agent）的**只读**诊断工具。回答「库里现在到底有什么」：
已索引多少篇、多少块、索引状态与当前切块配方是否一致。本地目录语料已退役，
不再扫描磁盘、也不再报告幽灵块/未入库。

不写任何东西、不触发重扫。发现不一致时让用户在知识库页重新索引。
"""
from biopilot.engine.tool import Tool, ToolResult
from biopilot.engine.rag.services.rag_service import get_rag_service
from biopilot.engine.tool.services.runtime_context import get_rag_domain


class IndexStatusTool(Tool):
    """索引体检（只读，不触发写入）。

    Attributes:
        name: str，工具名 "index_status"
        description: str，工具描述
        parameters: dict，JSON Schema（无参数）
        risk_level: str，"low"（只读）
        side_effects: list[str]，["read_file"]（读索引状态与向量库元数据）
    """

    name = "index_status"
    description = (
        "体检平台论文索引：报告已索引文档数与块数、索引状态与当前切块配方是否一致。"
        "只读、不触发重建。用户问「索引里有什么 / 索引好像不对 / 是不是漏了几篇」时先用它；"
        "需要重建时让用户在知识库页操作（勾选/重试/全部重新索引）。")
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = "low"
    side_effects = ["read_file"]

    def execute(self) -> ToolResult:
        """取一次索引体检快照并格式化成文本。

        Returns:
            ToolResult，文本为各项计数与不一致清单；服务不可用时返回错误文本
            （不中断调用方流程，由上级决定是否请示用户）。
        """
        try:
            st = get_rag_service(user_domain=get_rag_domain()).index_status()
        except Exception as e:
            # 外部服务缺席如实回报，不让异常穿透 ReAct 循环
            return ToolResult(text=f"索引体检失败：{e}", is_error=True)

        lines = [
            f"向量库：{'可连' if st.milvus_ok else '不可连（库侧计数不可用，建议先起 Milvus）'}"
            + (f"，{st.store_chunks} 块 / {st.store_docs} 篇" if st.milvus_ok else ""),
            f"关键词索引（BM25）：{st.bm25_docs} 篇" if st.milvus_ok else "关键词索引：未读（库不可连）",
        ]
        if not st.state_present:
            lines.append("索引状态：不存在或不可解析（从未建过索引或状态损坏）")
        else:
            lines.append(f"索引状态：记录 {st.indexed_docs} 篇")
            lines.append(
                "切块配方：与当前配置一致" if st.recipe_in_sync
                else "切块配方：**与当前配置不一致**（切块参数或解析逻辑改过）"
                     "→ 让用户在知识库页点「全部重新索引」")

        return ToolResult(text="\n".join(lines), summary={
            "milvus_ok": st.milvus_ok, "recipe_in_sync": st.recipe_in_sync,
            "indexed_docs": st.indexed_docs,
            "store_chunks": st.store_chunks, "store_docs": st.store_docs,
            "bm25_docs": st.bm25_docs})
