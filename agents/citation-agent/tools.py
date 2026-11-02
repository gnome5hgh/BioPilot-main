"""citation-agent 的工具装配：引用管理全家桶 + 读 PDF，不给文件写工具。

文献库维护 agent：bib 的所有写入经 CitationManager（追加/删除/同步都是
托管操作），不需要裸文件工具；不装配 spawn（叶子 agent 不递归调度）、
不装配 RAG 检索（不读论文内容做分析）。read_pdf 用于元数据缺失时读首页
取作者/年份（读元数据不属于「读论文内容做分析」），只要标题则用更轻的
extract_title。
删除目标不明确时不要猜：把候选与缺口写进结果交上级定夺（删除动作本身仍由
策略引擎向用户逐次确认，与提问无关）。

引用库按用户隔离：这里注入的是作用域代理，每次调用按当前 run 的 user_id
取对应 BibTeX 文件；写操作额外加 MySQL 命名锁，防网页与终端进程同时改同一份。
"""
from biopilot.citations import get_citation_manager
from biopilot.config import BioPilotConfig
from biopilot.tools.citations import (LookupCitationTool, AddCitationTool,
                                       FormatCitationsTool, ListCitationsTool,
                                       SyncCitationsTool, RemoveCitationTool)
from biopilot.tools import ExtractTitleTool, ReadPdfTool
from biopilot.cli.services.tool_assembly import make_tools
from biopilot.tools.recall import get_recall_tools


class ScopedCitationManager:
    """按当前用户域解析 CitationManager 的代理；写方法带跨进程命名锁。"""

    #: 会改 bib 文件的方法：需要跨进程互斥
    _WRITE_METHODS = {"add_from_pdf", "add_external", "remove", "sync_all"}

    def __init__(self, config):
        """记录全局配置，真正的 manager 在每次调用时按用户域取。"""
        self._config = config

    def _domain(self) -> str:
        """取当前 run 的用户域；未绑定时回退 local。"""
        try:
            from biopilot.tools.memory.runtime_context import get_memory_context
            ctx = get_memory_context()
            return getattr(ctx, "user_id", None) or "local"
        except Exception:
            return "local"

    def _manager(self):
        """当前用户域的 CitationManager。"""
        return get_citation_manager(self._config, user_domain=self._domain())

    def _with_lock(self, name: str, *args, **kwargs):
        """持命名锁执行写方法；拿不到锁时如实失败，不排队阻塞。"""
        from biopilot.core.memory.storage.named_lock import NamedLock
        domain = self._domain()
        lock_name = f"citation:{domain}"
        lock = NamedLock(self._config.runtime.memory_dsn)
        acquired = False
        try:
            acquired = lock.acquire(lock_name, timeout=5)
            if not acquired:
                raise RuntimeError("引用库正在被另一个进程修改，请稍后重试")
            return getattr(self._manager(), name)(*args, **kwargs)
        finally:
            if acquired:
                lock.release(lock_name)

    def __getattr__(self, name):
        """读方法直接委托；写方法包一层命名锁。"""
        if name in self._WRITE_METHODS:
            return lambda *args, **kwargs: self._with_lock(name, *args, **kwargs)
        return getattr(self._manager(), name)


_cm = ScopedCitationManager(BioPilotConfig.from_env())

TOOLS = make_tools(BioPilotConfig.from_env(), [
    LookupCitationTool(_cm), AddCitationTool(_cm),
    FormatCitationsTool(_cm), ListCitationsTool(_cm),
    SyncCitationsTool(_cm), RemoveCitationTool(_cm),
    ExtractTitleTool,                       # 只要标题时走轻路径，不必读整篇
    ReadPdfTool,                            # 元数据缺失时读首页取作者/年份
]) + get_recall_tools()
