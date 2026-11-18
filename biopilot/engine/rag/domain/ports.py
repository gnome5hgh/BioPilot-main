"""RAG 域的端口定义（领域层）：编码 / 精排 / 图表原图存取的契约。

三个协议的定义从原实现文件上收至此——端口属于领域层词汇，实现（``adapters/``）
与本文件解耦后，应用层（indexer/retriever/rag_service）只 import 本模块就能声明
其依赖形状，测试替身（FakeEmbedder/FakeReranker/内存 ImageStore）按结构化类型
天然满足，无需继承。
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol

from biopilot.engine.llm.adapters.api import ModelClient

if TYPE_CHECKING:  # numpy 仅作类型词汇；domain 层运行时零第三方依赖
    import numpy as np

__all__ = ["Embedder", "Reranker", "ImageStore", "VectorStore", "IndexStateStore",
           "PdfExtractor", "FigureExtractor", "FigureDescriberPort", "RagComponents"]


class Embedder(Protocol):
    """稠密编码协议：文本批次 → L2 归一化向量矩阵。

    Attributes:
        dim: int，模型输出的向量维度（只读静态表，不发网络探测）
    """

    def __call__(self, texts: list[str]) -> "np.ndarray":
        """把一批文本编码成 (len(texts), dim) 的归一化向量矩阵。

        Args:
            texts: list[str]，待编码的文本批次

        Returns:
            (len(texts), dim) 的 L2 归一化向量矩阵；空输入返回零行矩阵。
        """
        ...

    @property
    def dim(self) -> int:
        """模型输出的向量维度。"""
        ...


class Reranker(Protocol):
    """精排协议：query + 候选文档 → 按相关度降序的下标列表。"""

    def __call__(self, query: str, docs: list[str], top_k: int) -> list[int]:
        """按相关度对候选文档排序。

        Args:
            query: str，查询文本
            docs: list[str]，候选文档列表
            top_k: int，最多返回的下标个数

        Returns:
            按相关度降序的文档下标列表（长度 ≤ top_k）。
        """
        ...


class ImageStore(Protocol):
    """图表原图的存取接口（生产用对象存储，测试用内存替身）。

    Attributes:
        enabled: bool，这个存取器是否真的会存图。空实现为 False——调用方据此决定
            要不要去做「渲染 + 上传」这串昂贵动作（只问这个，不必再翻配置开关）。
    """

    enabled: bool

    def put(self, key: str, data: bytes) -> bool:
        """存入一张图。

        Args:
            key: 对象键（用块 id）。
            data: PNG 字节。

        Returns:
            bool: 是否存入成功。
        """
        ...

    def get(self, key: str) -> bytes | None:
        """按键取回一张图。

        Args:
            key: 对象键。

        Returns:
            bytes | None: 图片字节；对象不存在或存储不可用时为 None。
        """
        ...

    def remove(self, key: str) -> None:
        """按键删除一张图（对象不存在也算成功）。

        Args:
            key: 对象键。
        """
        ...

    def list_keys(self) -> list[str]:
        """列出图片命名空间下的全部逻辑键（供全量收敛找出孤儿对象）。

        Returns:
            list[str]: 逻辑键列表（不含 ``rag/images/`` 前缀）；存储不可用时为空列表。
        """
        ...


class VectorStore(Protocol):
    """向量库契约（Milvus Lite / Standalone 双模实现）。"""

    def add(self, ids: list[str], documents: list[str], vectors) -> None:
        """按 id 写入块文档与向量（重复 id 幂等覆盖）。"""
        ...

    def query(self, vector, top_k: int, filter_ids=None) -> list[dict]:
        """按向量近邻检索候选块。"""
        ...

    def delete(self, ids: list[str]) -> None:
        """按 id 删除块。"""
        ...

    def fetch_by_ids(self, ids: list[str]) -> list[dict]:
        """按 id 取块行（对账用）。"""
        ...

    def all_documents(self) -> dict[str, str]:
        """全部「块 id → 文档标识」映射（孤儿收敛用）。"""
        ...

    def count(self) -> int:
        """当前 collection 的块总数。"""
        ...


class IndexStateStore(Protocol):
    """增量索引状态契约（MySQL 实现；库不可达时进程内实现兜底）。"""

    def read(self) -> tuple[object, dict] | None:
        """读（配方指纹, 文档标识 → 指纹映射）；无状态返回 None。"""
        ...

    def write(self, recipe: object, docs: dict) -> None:
        """整体写入状态。"""
        ...

    def clear(self) -> None:
        """清空状态（配方变更触发全量重建）。"""
        ...

    def mutate(self, change) -> None:
        """持锁做一次读-改-写（``change(current) -> new``）。"""
        ...


class PdfExtractor(Protocol):
    """PDF 版面抽取契约（PyMuPDF 实现）。"""

    def extract(self, source: str, title: str = ""):
        """解析 PDF 文件路径为 ``PdfText``（标题由调用方提供，绝不取文件名）。"""
        ...

    def extract_bytes(self, data: bytes, title: str = "", *, digest: str = ""):
        """解析 PDF 字节为 ``PdfText``（平台论文不落盘）。"""
        ...


class FigureExtractor(Protocol):
    """图表定位与渲染契约（vision 域的无状态管线）。"""

    def extract(self, source, render_images: bool = True) -> list:
        """定位 PDF 里的图/表区域；``render_images=False`` 只定位不渲染。"""
        ...

    def render(self, source, figures) -> None:
        """就地把图像字节渲染进给定的 Figure 列表。"""
        ...


class FigureDescriberPort(Protocol):
    """检索用图注描述契约（vision 应用实现；视觉模型不可用时 available=False）。"""

    @property
    def available(self) -> bool:
        """视觉模型是否已配置。"""
        ...

    def describe(self, figure) -> str:
        """把一张区域图描述成一段检索用文本。"""
        ...


@dataclass(frozen=True)
class RagComponents:
    """RAG 组件的 provider 包：应用层只调用，构造收在 adapters 组装缝。

    每个字段都是惰性工厂——Milvus 连接、嵌入/精排客户端、状态库的「构造数秒、
    可能失败、软依赖降级」语义由 provider 保留；应用层 ``_ensure_*`` 的双检锁
    只缓存调用结果，不再触碰任何构造细节。
    """

    embedder: Callable[[], Embedder]
    reranker: Callable[[], Reranker]
    vector_store: Callable[[int], VectorStore]  # 入参 = 编码维度（建集合时定死）
    image_store: Callable[[], ImageStore]
    state_store: Callable[[], IndexStateStore]
    pdf_extractor: Callable[[], PdfExtractor]
    figure_extractor: Callable[[], FigureExtractor]
    figure_describer: Callable[[], FigureDescriberPort]
    rewriter_llm: Callable[[], ModelClient]
