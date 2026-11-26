# app-server/src/com/damon/ming/ai/rag/source/manager.py
"""集中管理数据源配置、文件路由和文档加载。"""

import os
from pathlib import Path
from typing import ClassVar

from llama_index.core import Document
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import (
    FILE_NAME,
    FILE_PATH,
    FILE_SHA256,
    SOURCE_REF_ID,
)
from src.com.damon.ming.ai.rag.source import SourceConfig, resolve_source
from src.com.damon.ming.ai.rag.source.base import BaseDataSource
from src.com.damon.ming.ai.rag.source.config_parser import SourceConfigParser
from src.com.damon.ming.ai.rag.source.image_text_extractor import configure_ocr
from src.com.damon.ming.ai.rag.source.legacy_office_converter import (
    LEGACY_OFFICE_EXTENSIONS,
    convert_legacy_office,
)
from src.com.damon.ming.log import pin
from src.com.damon.ming.security.digest import sha256_file

logger = pin("DataSourceManager")


class DataSourceManager:
    """按文件类型创建数据源，并统一提供目录和文件列表加载入口。"""

    _FIXED_EXTENSIONS: ClassVar[dict[str, frozenset[str]]] = {
        "csv": frozenset({".csv"}),
        "doc": frozenset({".doc", ".docx"}),
        "html": frozenset({".htm", ".html"}),
        "md": frozenset({".md"}),
        "pdf": frozenset({".pdf"}),
        "pptx": frozenset({".ppt", ".pptx"}),
        "xlsx": frozenset({".xls", ".xlsx"}),
    }

    def __init__(self) -> None:
        self._corpus_dir: Path | None = None
        self._config: SourceConfig | None = None

    def initialize(self, corpus_dir: Path, config: dict[str, object]) -> None:
        """初始化知识库目录和数据源配置。"""
        if self._config is not None:
            raise RuntimeError("数据源管理器已经初始化")
        config = SourceConfigParser.parse(config)
        configure_ocr(config.ocr.device)
        self._corpus_dir = Path(corpus_dir)
        self._corpus_dir.mkdir(parents=True, exist_ok=True)
        self._config = config

    def load_directory(self) -> list[Document]:
        """扫描目录一次，并将受支持的文件交给对应数据源解析。"""
        self._ensure_initialized()
        root_dir = self._corpus_dir
        if root_dir is None:
            raise RuntimeError("数据源管理器尚未初始化")

        file_paths: list[str] = []
        for root, directory_names, file_names in os.walk(root_dir):
            # 该目录保存 PDF、DOCX、PPTX 解析出的内嵌图片，不能再作为独立图片重复入库。
            directory_names[:] = [
                directory_name
                for directory_name in directory_names
                if directory_name.lower() != "images"
            ]
            file_paths.extend(str(Path(root) / file_name) for file_name in file_names)
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
            modern_paths = [
                file_path
                for file_path in paths
                if Path(file_path).suffix.lower() not in LEGACY_OFFICE_EXTENSIONS
            ]
            if modern_paths:
                documents.extend(source.load_specific_files(modern_paths))

            for file_path in paths:
                if Path(file_path).suffix.lower() not in LEGACY_OFFICE_EXTENSIONS:
                    continue
                documents.extend(
                    self._load_legacy_office_file(engine, file_path, source, config)
                )
        return documents

    @staticmethod
    def _load_legacy_office_file(
        engine: str,
        file_path: str,
        source: BaseDataSource,
        config: SourceConfig,
    ) -> list[Document]:
        """转换并解析旧版 Office，同时把文档身份恢复为原始文件。"""
        original_path = Path(file_path).resolve()
        try:
            with convert_legacy_office(
                original_path,
                config.legacy_office_source.conversion_timeout_seconds,
            ) as converted_path:
                documents = source.load_specific_files([str(converted_path)])

            original_sha256 = sha256_file(str(original_path))
            for document in documents:
                document.metadata.update(
                    {
                        FILE_NAME: original_path.name,
                        FILE_PATH: str(original_path),
                        FILE_SHA256: original_sha256,
                        SOURCE_REF_ID: original_sha256,
                    }
                )
            return documents
        except Exception:
            logger.exception(
                f"[DataSourceManager] 旧版 Office 文件转换或解析失败 | "
                f"engine={engine} | file={original_path}"
            )
            return []

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
