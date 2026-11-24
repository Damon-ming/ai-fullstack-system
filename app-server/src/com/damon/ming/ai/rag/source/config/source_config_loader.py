# app-server/src/com/damon/ming/ai/rag/source/config/source_config_loader.py
"""
数据源配置加载器 —— 从 YAML 读取各数据源类型的可配置参数。

本模块属于 source/ 配置子模块。
LocalTextDataSource 通过 SourceConfig 数据类接收参数，不感知配置来源。

配置项：
  - text_source.extensions: 文本数据源支持的文件扩展名
  - text_source.pre_chunk: 大文件预分块配置（边界优先级 + 块大小）

用法：
  loader = SourceConfigLoader()
  config = loader.load()                          # SourceConfig 实例
  config.text_source.extensions                   # {".txt", ".md"}
  config.text_source.pre_chunk.enabled            # True
  config.text_source.pre_chunk.chunk_chars        # 500
  config.text_source.pre_chunk.boundaries         # ["\\n\\n", "\\n", ""]
"""

import os
from dataclasses import dataclass

from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


@dataclass(frozen=True)
class PreChunkConfig:
    """预分块配置（纯数据类）。

    大文本文件在入库前按自然边界预分块，使每个 Document 粒度合理，
    避免检索时章节重建拉回全文。

    每个 pre-chunk 作为独立 Document 进入后续 splitter 流程，
    各自获得独立 section_id，检索时各自命中，因此块间不需要 overlap。
    """

    # 是否启用预分块
    enabled: bool

    # 每个预分块的目标字符数（超过此长度会触发切分）
    chunk_chars: int

    # 切分边界优先级列表（从高到低尝试）
    # 空字符串 "" 兜底表示"按固定长度硬切"
    # 常用边界：
    #   "\\n\\n"  → 段落分隔（空行）
    #   "\\n"     → 换行
    #   "。！？"  → 中文句末标点
    #   ".,!?"   → 英文句末标点
    #   " "      → 空格
    #   ""       → 字符级兜底
    boundaries: tuple[str, ...]


@dataclass(frozen=True)
class TextSourceConfig:
    """文本数据源配置（纯数据类）。"""

    # 支持的文件扩展名（带点号，小写）
    extensions: set[str]

    # 大文件预分块配置
    pre_chunk: PreChunkConfig


@dataclass(frozen=True)
class CsvSourceConfig:
    """CSV 数据源配置（纯数据类）。"""

    # 每个 Document 包含的数据行数（不含表头）
    batch_rows: int


@dataclass(frozen=True)
class XlsxSourceConfig:
    """XLSX 数据源配置（纯数据类）。"""

    # 每个 Document 包含的数据行数（不含表头）
    batch_rows: int


@dataclass(frozen=True)
class ImageSourceConfig:
    """独立图片数据源配置。"""

    # 支持的图片文件扩展名（带点号，小写）
    extensions: set[str]


@dataclass(frozen=True)
class OcrConfig:
    """OCR 推理设备配置。"""

    device: str


@dataclass(frozen=True)
class MarkdownSourceConfig:
    """Markdown 数据源配置（纯数据类）。"""

    # 超大标题段落的二次切分配置
    pre_chunk: PreChunkConfig


@dataclass(frozen=True)
class PdfSourceConfig:
    """PDF 数据源配置（纯数据类）。"""

    # 是否从文本型 PDF 的嵌入图片中提取文字
    enable_image_extract: bool


@dataclass(frozen=True)
class DocSourceConfig:
    """DOCX 数据源配置（纯数据类）。"""

    # 预分块配置（超大段落按自然边界切分）
    pre_chunk: PreChunkConfig

    # 是否提取表格为 Markdown 表格
    include_tables: bool


@dataclass(frozen=True)
class PptxSourceConfig:
    """PPTX 数据源配置（纯数据类）。"""

    # 预分块配置（超大文本按自然边界切分）
    pre_chunk: PreChunkConfig

    # 是否提取表格为 Markdown 表格
    include_tables: bool

    # 是否提取演讲者备注
    include_notes: bool

    # 是否提取图片并 OCR
    extract_images: bool


@dataclass(frozen=True)
class HtmlSourceConfig:
    """HTML 数据源配置（纯数据类）。"""

    # 预分块配置（超大正文按自然边界切分）
    pre_chunk: PreChunkConfig

    # 是否保留超链接 URL
    include_links: bool

    # 是否提取 HTML 表格
    include_tables: bool


@dataclass(frozen=True)
class SourceConfig:
    """数据源总配置（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。"""

    # CSV 数据源配置
    csv_source: CsvSourceConfig

    # XLSX 数据源配置
    xlsx_source: XlsxSourceConfig

    # 图片数据源配置
    image_source: ImageSourceConfig

    # OCR 推理配置（PDF、Office 内嵌图片和独立图片共用）
    ocr: OcrConfig

    # 文本数据源配置
    text_source: TextSourceConfig

    # Markdown 数据源配置
    markdown_source: MarkdownSourceConfig

    # PDF 数据源配置
    pdf_source: PdfSourceConfig

    # DOC/DOCX 数据源配置
    doc_source: DocSourceConfig

    # PPTX 数据源配置
    pptx_source: PptxSourceConfig

    # HTML 数据源配置
    html_source: HtmlSourceConfig


class SourceConfigLoader:
    """从 YAML 文件加载数据源配置。

    启动时全量加载，所有配置在服务启动阶段初始化完毕。
    """

    _cache: SourceConfig | None = None

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load(self) -> SourceConfig:
        """加载数据源配置。

        Returns:
            SourceConfig 数据类实例。
        """
        if self._cache is not None:
            return self._cache

        raw = self._read_yaml()
        csv_section = self._required_section(raw, "csv_source")
        xlsx_section = self._required_section(raw, "xlsx_source")
        image_section = self._required_section(raw, "image_source")
        ocr_section = self._required_section(raw, "ocr")
        text_section = self._required_section(raw, "text_source")
        markdown_section = self._required_section(raw, "markdown_source")
        pdf_section = self._required_section(raw, "pdf_source")
        doc_section = self._required_section(raw, "doc_source")
        pptx_section = self._required_section(raw, "pptx_source")
        html_section = self._required_section(raw, "html_source")

        extensions_raw = self._required_value(text_section, "extensions", "text_source")
        if not isinstance(extensions_raw, list) or not all(
            isinstance(extension, str) for extension in extensions_raw
        ):
            raise TypeError("text_source.extensions 必须是字符串列表")
        image_extensions_raw = self._required_value(
            image_section, "extensions", "image_source"
        )
        if not isinstance(image_extensions_raw, list) or not all(
            isinstance(extension, str) for extension in image_extensions_raw
        ):
            raise TypeError("image_source.extensions 必须是字符串列表")
        if not image_extensions_raw:
            raise ValueError("image_source.extensions 不能为空")
        ocr_device = self._required_value(ocr_section, "device", "ocr")
        if not isinstance(ocr_device, str) or ocr_device not in {"cpu", "gpu"}:
            raise ValueError("ocr.device 只支持 'cpu' 或 'gpu'")

        pdf_enable_image_extract = self._required_value(
            pdf_section, "enable_image_extract", "pdf_source"
        )
        doc_include_tables = self._required_value(
            doc_section, "include_tables", "doc_source"
        )
        pptx_include_tables = self._required_value(
            pptx_section, "include_tables", "pptx_source"
        )
        pptx_include_notes = self._required_value(
            pptx_section, "include_notes", "pptx_source"
        )
        pptx_extract_images = self._required_value(
            pptx_section, "extract_images", "pptx_source"
        )
        html_include_links = self._required_value(
            html_section, "include_links", "html_source"
        )
        html_include_tables = self._required_value(
            html_section, "include_tables", "html_source"
        )

        self._validate_bool(pdf_enable_image_extract, "pdf_source.enable_image_extract")
        self._validate_bool(doc_include_tables, "doc_source.include_tables")
        self._validate_bool(pptx_include_tables, "pptx_source.include_tables")
        self._validate_bool(pptx_include_notes, "pptx_source.include_notes")
        self._validate_bool(pptx_extract_images, "pptx_source.extract_images")
        self._validate_bool(html_include_links, "html_source.include_links")
        self._validate_bool(html_include_tables, "html_source.include_tables")

        self._cache = SourceConfig(
            csv_source=CsvSourceConfig(
                batch_rows=self._required_positive_int(
                    csv_section, "batch_rows", "csv_source"
                ),
            ),
            xlsx_source=XlsxSourceConfig(
                batch_rows=self._required_positive_int(
                    xlsx_section, "batch_rows", "xlsx_source"
                ),
            ),
            image_source=ImageSourceConfig(extensions=set(image_extensions_raw)),
            ocr=OcrConfig(device=ocr_device),
            text_source=TextSourceConfig(
                extensions=set(extensions_raw),
                pre_chunk=self._parse_pre_chunk(text_section, "text_source"),
            ),
            markdown_source=MarkdownSourceConfig(
                pre_chunk=self._parse_pre_chunk(markdown_section, "markdown_source"),
            ),
            pdf_source=PdfSourceConfig(
                enable_image_extract=pdf_enable_image_extract,
            ),
            doc_source=DocSourceConfig(
                pre_chunk=self._parse_pre_chunk(doc_section, "doc_source"),
                include_tables=doc_include_tables,
            ),
            pptx_source=PptxSourceConfig(
                pre_chunk=self._parse_pre_chunk(pptx_section, "pptx_source"),
                include_tables=pptx_include_tables,
                include_notes=pptx_include_notes,
                extract_images=pptx_extract_images,
            ),
            html_source=HtmlSourceConfig(
                pre_chunk=self._parse_pre_chunk(html_section, "html_source"),
                include_links=html_include_links,
                include_tables=html_include_tables,
            ),
        )
        return self._cache

    @staticmethod
    def _required_section(parent: dict, key: str) -> dict:
        section = parent.get(key)
        if not isinstance(section, dict):
            raise ValueError(f"缺少有效的 {key} 配置项")
        return section

    @staticmethod
    def _required_value(section: dict, key: str, section_name: str):
        if key not in section or section[key] is None:
            raise ValueError(f"缺少 {section_name}.{key} 配置项")
        return section[key]

    @classmethod
    def _parse_pre_chunk(cls, source_section: dict, source_name: str) -> PreChunkConfig:
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

        return PreChunkConfig(
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

    def _read_yaml(self) -> dict:
        raw_cfg = load_yaml(self._config_path)
        if raw_cfg is None or not isinstance(raw_cfg, dict):
            raise ValueError("数据源配置文件格式错误：需要顶层键值对")
        return raw_cfg
