# app-server/src/com/damon/ming/ai/source/base.py
"""
数据源抽象基类 —— 所有数据源实现继承此类。

本模块只定义接口，不感知具体文件格式、线程池、取消令牌等基础设施。
"""

from abc import ABC, abstractmethod

from llama_index.core import Document


class BaseDataSource(ABC):
    """数据源抽象：仅负责加载原始文档"""

    @abstractmethod
    def load_documents(self) -> list[Document]:
        pass

    @abstractmethod
    def load_specific_files(self, file_paths: list[str]) -> list[Document]:
        pass
