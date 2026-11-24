# app-server/src/com/damon/ming/ai/rag/source/manager.py
"""集中管理数据源配置、文件路由和文档加载。"""

import os
from pathlib import Path
from typing import ClassVar

from llama_index.core import Document
from src.com.damon.ming.ai.rag.source import resolve_source
from src.com.damon.ming.ai.rag.source.config.source_config_loader import (
    SourceConfig,
    SourceConfigLoader,
)


class DataSourceManager:
    """按文件类型创建数据源，并统一提供目录和文件列表加载入口。"""

    _FIXED_EXTENSIONS: ClassVar[dict[str, frozenset[str]]] = {
        "csv": frozenset({".csv"}),
        "doc": frozenset({".docx"}),
        "html": frozenset({".htm", ".html"}),
        "md": frozenset({".md"}),
        "pdf": frozenset({".pdf"}),
        "pptx": frozenset({".pptx"}),
        "xlsx": frozenset({".xlsx"}),
    }

    def __init__(self) -> None:
        self._corpus_dir: Path | None = None
        self._config: SourceConfig | None = None

    def initialize(self, corpus_dir: Path) -> None:
        """初始化知识库目录和数据源配置。"""
        if self._config is not None:
            raise RuntimeError("数据源管理器已经初始化")
        self._corpus_dir = Path(corpus_dir)
        self._corpus_dir.mkdir(parents=True, exist_ok=True)
        self._config = SourceConfigLoader().load()

    def load_directory(self) -> list[Document]:
        """扫描目录一次，并将受支持的文件交给对应数据源解析。"""
        self._ensure_initialized()
        root_dir = self._corpus_dir
        if root_dir is None:
            raise RuntimeError("数据源管理器尚未初始化")

        file_paths = [
            str(Path(root) / file_name)
            for root, _, file_names in os.walk(root_dir)
            for file_name in file_names
        ]
        return self.load_files(file_paths)

    def load_files(self, file_paths: list[str]) -> list[Document]:
        """按扩展名分发指定文件，只创建本批次实际需要的数据源。"""
        config = self._ensure_initialized()
        files_by_engine = self._group_file_paths(file_paths, config)
        documents: list[Document] = []

        for engine, paths in files_by_engine.items():
            source = resolve_source(engine)(
                str(self._corpus_dir), **self._engine_config(engine, config)
            )
            documents.extend(source.load_specific_files(paths))
        return documents

    def _group_file_paths(
        self, file_paths: list[str], config: SourceConfig
    ) -> dict[str, list[str]]:
        extensions_by_engine = {
            **self._FIXED_EXTENSIONS,
            "image": config.image_source.extensions,
            "text": config.text_source.extensions,
        }
        grouped: dict[str, list[str]] = {}
        for file_path in file_paths:
            extension = Path(file_path).suffix.lower()
            for engine, extensions in extensions_by_engine.items():
                if extension in extensions:
                    grouped.setdefault(engine, []).append(file_path)
                    break
        return grouped

    @staticmethod
    def _engine_config(engine: str, config: SourceConfig) -> dict:
        """将已加载的不可变配置注入本次调用使用的数据源实例。"""
        configs = {
            "csv": {"batch_rows": config.csv_source.batch_rows},
            "doc": {
                "pre_chunk_config": config.doc_source.pre_chunk,
                "include_tables": config.doc_source.include_tables,
            },
            "html": {
                "pre_chunk_config": config.html_source.pre_chunk,
                "include_links": config.html_source.include_links,
                "include_tables": config.html_source.include_tables,
            },
            "image": {"supported_extensions": config.image_source.extensions},
            "md": {"pre_chunk_config": config.markdown_source.pre_chunk},
            "pptx": {
                "pre_chunk_config": config.pptx_source.pre_chunk,
                "include_tables": config.pptx_source.include_tables,
                "include_notes": config.pptx_source.include_notes,
                "extract_images": config.pptx_source.extract_images,
            },
            "pdf": {
                "enable_image_extract": config.pdf_source.enable_image_extract,
            },
            "text": {
                "supported_extensions": config.text_source.extensions,
                "pre_chunk_config": config.text_source.pre_chunk,
            },
            "xlsx": {"batch_rows": config.xlsx_source.batch_rows},
        }
        return configs.get(engine, {})

    def _ensure_initialized(self) -> SourceConfig:
        if self._config is None or self._corpus_dir is None:
            raise RuntimeError("数据源管理器尚未初始化")
        return self._config
