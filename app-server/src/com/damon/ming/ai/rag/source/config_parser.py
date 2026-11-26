"""解析 RagRuntime 中的数据源配置。"""

from src.com.damon.ming.ai.rag.source.config import (
    CsvSourceParams,
    DocSourceParams,
    HtmlSourceParams,
    ImageSourceParams,
    LegacyOfficeSourceParams,
    MarkdownSourceParams,
    OcrParams,
    PdfSourceParams,
    PptxSourceParams,
    PreChunkParams,
    SourceConfig,
    TextSourceParams,
    XlsxSourceParams,
)


class SourceConfigParser:
    """校验并构造数据源配置。"""

    @classmethod
    def parse(cls, raw: dict) -> SourceConfig:
        if not isinstance(raw, dict):
            raise TypeError("数据源配置必须是键值对象")
        csv_section = cls._required_section(raw, "csv_source")
        xlsx_section = cls._required_section(raw, "xlsx_source")
        image_section = cls._required_section(raw, "image_source")
        ocr_section = cls._required_section(raw, "ocr")
        legacy_office_section = cls._required_section(raw, "legacy_office_source")
        text_section = cls._required_section(raw, "text_source")
        markdown_section = cls._required_section(raw, "markdown_source")
        pdf_section = cls._required_section(raw, "pdf_source")
        doc_section = cls._required_section(raw, "doc_source")
        pptx_section = cls._required_section(raw, "pptx_source")
        html_section = cls._required_section(raw, "html_source")

        extensions_raw = cls._required_value(text_section, "extensions", "text_source")
        if not isinstance(extensions_raw, list) or not all(
            isinstance(extension, str) for extension in extensions_raw
        ):
            raise TypeError("text_source.extensions 必须是字符串列表")
        image_extensions_raw = cls._required_value(
            image_section, "extensions", "image_source"
        )
        if not isinstance(image_extensions_raw, list) or not all(
            isinstance(extension, str) for extension in image_extensions_raw
        ):
            raise TypeError("image_source.extensions 必须是字符串列表")
        if not image_extensions_raw:
            raise ValueError("image_source.extensions 不能为空")
        ocr_device = cls._required_value(ocr_section, "device", "ocr")
        if not isinstance(ocr_device, str) or ocr_device not in {"cpu", "gpu"}:
            raise ValueError("ocr.device 只支持 'cpu' 或 'gpu'")

        pdf_enable_image_extract = cls._required_value(
            pdf_section, "enable_image_extract", "pdf_source"
        )
        doc_include_tables = cls._required_value(
            doc_section, "include_tables", "doc_source"
        )
        pptx_include_tables = cls._required_value(
            pptx_section, "include_tables", "pptx_source"
        )
        pptx_include_notes = cls._required_value(
            pptx_section, "include_notes", "pptx_source"
        )
        pptx_extract_images = cls._required_value(
            pptx_section, "extract_images", "pptx_source"
        )
        html_include_links = cls._required_value(
            html_section, "include_links", "html_source"
        )
        html_include_tables = cls._required_value(
            html_section, "include_tables", "html_source"
        )

        cls._validate_bool(pdf_enable_image_extract, "pdf_source.enable_image_extract")
        cls._validate_bool(doc_include_tables, "doc_source.include_tables")
        cls._validate_bool(pptx_include_tables, "pptx_source.include_tables")
        cls._validate_bool(pptx_include_notes, "pptx_source.include_notes")
        cls._validate_bool(pptx_extract_images, "pptx_source.extract_images")
        cls._validate_bool(html_include_links, "html_source.include_links")
        cls._validate_bool(html_include_tables, "html_source.include_tables")

        config = SourceConfig(
            csv_source=CsvSourceParams(
                batch_rows=cls._required_positive_int(
                    csv_section, "batch_rows", "csv_source"
                ),
            ),
            xlsx_source=XlsxSourceParams(
                batch_rows=cls._required_positive_int(
                    xlsx_section, "batch_rows", "xlsx_source"
                ),
            ),
            image_source=ImageSourceParams(extensions=set(image_extensions_raw)),
            ocr=OcrParams(device=ocr_device),
            legacy_office_source=LegacyOfficeSourceParams(
                conversion_timeout_seconds=cls._required_positive_int(
                    legacy_office_section,
                    "conversion_timeout_seconds",
                    "legacy_office_source",
                ),
            ),
            text_source=TextSourceParams(
                extensions=set(extensions_raw),
                pre_chunk=cls._parse_pre_chunk(text_section, "text_source"),
            ),
            markdown_source=MarkdownSourceParams(
                pre_chunk=cls._parse_pre_chunk(markdown_section, "markdown_source"),
            ),
            pdf_source=PdfSourceParams(
                enable_image_extract=pdf_enable_image_extract,
            ),
            doc_source=DocSourceParams(
                pre_chunk=cls._parse_pre_chunk(doc_section, "doc_source"),
                include_tables=doc_include_tables,
            ),
            pptx_source=PptxSourceParams(
                pre_chunk=cls._parse_pre_chunk(pptx_section, "pptx_source"),
                include_tables=pptx_include_tables,
                include_notes=pptx_include_notes,
                extract_images=pptx_extract_images,
            ),
            html_source=HtmlSourceParams(
                pre_chunk=cls._parse_pre_chunk(html_section, "html_source"),
                include_links=html_include_links,
                include_tables=html_include_tables,
            ),
        )
        return config

    @staticmethod
    def _required_section(parent: dict, key: str) -> dict:
        section = parent.get(key)
        if not isinstance(section, dict):
            raise TypeError(f"缺少有效的 {key} 配置项")
        return section

    @staticmethod
    def _required_value(section: dict, key: str, section_name: str):
        if key not in section or section[key] is None:
            raise ValueError(f"缺少 {section_name}.{key} 配置项")
        return section[key]

    @classmethod
    def _parse_pre_chunk(cls, source_section: dict, source_name: str) -> PreChunkParams:
        section = cls._required_section(source_section, "pre_chunk")
        enabled = cls._required_value(section, "enabled", f"{source_name}.pre_chunk")
        chunk_chars = cls._required_value(
            section, "chunk_chars", f"{source_name}.pre_chunk"
        )
        boundaries_raw = cls._required_value(
            section, "boundaries", f"{source_name}.pre_chunk"
        )
        cls._validate_bool(enabled, f"{source_name}.pre_chunk.enabled")
        if type(chunk_chars) is not int or chunk_chars <= 0:
            raise ValueError(f"{source_name}.pre_chunk.chunk_chars 必须是正整数")
        if not isinstance(boundaries_raw, list) or not all(
            isinstance(boundary, str) for boundary in boundaries_raw
        ):
            raise TypeError(f"{source_name}.pre_chunk.boundaries 必须是字符串列表")
        if not boundaries_raw:
            raise ValueError(f"{source_name}.pre_chunk.boundaries 不能为空")

        return PreChunkParams(
            enabled=enabled,
            chunk_chars=chunk_chars,
            boundaries=tuple(boundaries_raw),
        )

    @classmethod
    def _required_positive_int(cls, section: dict, key: str, section_name: str) -> int:
        value = cls._required_value(section, key, section_name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{section_name}.{key} 必须是正整数")
        return value

    @staticmethod
    def _validate_bool(value, config_path: str) -> None:
        if not isinstance(value, bool):
            raise TypeError(f"{config_path} 必须是布尔值")
