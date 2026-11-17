"""RAG 域的端口定义（领域层）：编码 / 精排 / 图表原图存取的契约。

三个协议的定义从原实现文件上收至此——端口属于领域层词汇，实现（``adapters/``）
与本文件解耦后，应用层（indexer/retriever/rag_service）只 import 本模块就能声明
其依赖形状，测试替身（FakeEmbedder/FakeReranker/内存 ImageStore）按结构化类型
天然满足，无需继承。
"""
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # numpy 仅作类型词汇；domain 层运行时零第三方依赖
    import numpy as np

__all__ = ["Embedder", "Reranker", "ImageStore"]


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
