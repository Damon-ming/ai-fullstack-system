"""数据源配置对象，由 RagRuntime 构造并注入。"""

from dataclasses import dataclass


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
class LegacyOfficeSourceConfig:
    """旧版 Office 转换配置。"""

    conversion_timeout_seconds: int


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
    """数据源总配置（纯数据类）。所有参数由应用配置显式提供，无内置默认值。"""

    # CSV 数据源配置
    csv_source: CsvSourceConfig

    # XLSX 数据源配置
    xlsx_source: XlsxSourceConfig

    # 图片数据源配置
    image_source: ImageSourceConfig

    # OCR 推理配置（PDF、Office 内嵌图片和独立图片共用）
    ocr: OcrConfig

    # 旧版 Office 转换配置
    legacy_office_source: LegacyOfficeSourceConfig

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
