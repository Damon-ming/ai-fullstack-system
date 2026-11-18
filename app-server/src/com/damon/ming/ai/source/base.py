# app-server/src/com/damon/ming/ai/source/base.py
"""
数据源抽象基类 —— 所有数据源实现继承此类。

本模块只定义接口，不感知具体文件格式、线程池、取消令牌等基础设施。
"""

from abc import ABC, abstractmethod

from llama_index.core import Document


class BaseDataSource(ABC):
    """数据源抽象：统一数据目录，并负责加载原始文档。"""

    def __init__(self, folder_path: str) -> None:
        """初始化数据源目录，所有实现类共享此构造约定。"""
        self.folder_path = folder_path

    @abstractmethod
    def load_documents(self) -> list[Document]:
        pass

    @abstractmethod
    def load_specific_files(self, file_paths: list[str]) -> list[Document]:
        pass
