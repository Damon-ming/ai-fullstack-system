# app-server/src/com/damon/ming/ai/source/pdf/base_pdf.py
"""
PDF 解析器抽象基类 —— 所有 PDF 解析策略实现继承此类。

契约：
    parse(file_path: str) -> list[Document]
    所有子类输出统一格式的 Document 列表，下游 RAG pipeline 不感知具体解析策略。
"""

from abc import ABC, abstractmethod

from llama_index.core import Document


class BasePdfParser(ABC):
    """PDF 解析器抽象接口。

    新增 PDF 解析策略只需：
        1. 继承此类，实现 parse()
        2. 在 pdf/__init__.py 的路由函数中加一条规则
    """

    @abstractmethod
    def parse(self, file_path: str) -> list[Document]:
        """解析单个 PDF 文件为 Document 列表。

        Args:
            file_path: PDF 文件的绝对路径。

        Returns:
            解析后的 Document 列表。解析失败返回空列表。
        """
