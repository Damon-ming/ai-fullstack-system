# app-server/src/com/damon/ming/ai/config/source/source_config_loader.py
"""
数据源配置加载器 —— 从 YAML 读取各数据源类型的可配置参数。

本模块属于 ai/config/source/ 配置子模块。
LocalTextDataSource 通过 SourceConfig 数据类接收参数，不感知配置来源。

配置项：
  - text_source.extensions: 文本数据源支持的文件扩展名
  - text_source.encoding_fallbacks: 文本编码尝试顺序
  - text_source.pre_chunk: 大文件预分块配置（边界优先级 + 块大小）

用法：
  loader = SourceConfigLoader()
  config = loader.load()                          # SourceConfig 实例
  config.text_source.extensions                   # {".txt", ".md"}
  config.text_source.encoding_fallbacks           # ("utf-8", "gbk", "latin-1")
  config.text_source.pre_chunk.enabled            # True
  config.text_source.pre_chunk.chunk_chars        # 500
  config.text_source.pre_chunk.boundaries         # ["\\n\\n", "\\n", ""]
"""

import os
from dataclasses import dataclass, field

import yaml


@dataclass(frozen=True)
class PreChunkConfig:
    """预分块配置（纯数据类）。

    大文本文件在入库前按自然边界预分块，使每个 Document 粒度合理，
    避免检索时章节重建拉回全文。

    每个 pre-chunk 作为独立 Document 进入后续 splitter 流程，
    各自获得独立 section_id，检索时各自命中，因此块间不需要 overlap。
    """

    # 是否启用预分块
    enabled: bool = True

    # 每个预分块的目标字符数（超过此长度会触发切分）
    chunk_chars: int = 500

    # 切分边界优先级列表（从高到低尝试）
    # 空字符串 "" 兜底表示"按固定长度硬切"
    # 常用边界：
    #   "\\n\\n"  → 段落分隔（空行）
    #   "\\n"     → 换行
    #   "。！？"  → 中文句末标点
    #   ".,!?"   → 英文句末标点
    #   " "      → 空格
    #   ""       → 字符级兜底
    boundaries: tuple[str, ...] = (
        "\n\n",
        "\n",
        "",
    )


@dataclass(frozen=True)
class TextSourceConfig:
    """文本数据源配置（纯数据类）。"""

    # 支持的文件扩展名（带点号，小写）
    extensions: set[str] = field(default_factory=set)

    # 文本编码尝试顺序
    encoding_fallbacks: tuple[str, ...] = field(default_factory=tuple)

    # 大文件预分块配置
    pre_chunk: PreChunkConfig = field(default_factory=PreChunkConfig)


@dataclass(frozen=True)
class CsvSourceConfig:
    """CSV 数据源配置（纯数据类）。"""

    # 编码尝试顺序
    encoding_fallbacks: tuple[str, ...]

    # 每个 Document 包含的数据行数（不含表头）
    batch_rows: int


@dataclass(frozen=True)
class XlsxSourceConfig:
    """XLSX 数据源配置（纯数据类）。"""

    # 每个 Document 包含的数据行数（不含表头）
    batch_rows: int


@dataclass(frozen=True)
class MarkdownSourceConfig:
    """Markdown 数据源配置（纯数据类）。"""

    # 编码尝试顺序
    encoding_fallbacks: tuple[str, ...] = field(default_factory=tuple)

    # 超大标题段落的二次切分配置
    pre_chunk: PreChunkConfig = field(default_factory=PreChunkConfig)


@dataclass(frozen=True)
class DocSourceConfig:
    """DOC/DOCX 数据源配置（纯数据类）。"""

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

    # 编码尝试顺序
    encoding_fallbacks: tuple[str, ...]

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

    # 文本数据源配置
    text_source: TextSourceConfig

    # Markdown 数据源配置
    markdown_source: MarkdownSourceConfig

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
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "source-config.yaml")
        self._config_path = config_path

    def load(self) -> SourceConfig:
        """加载数据源配置。

        Returns:
            SourceConfig 数据类实例。
        """
        if self._cache is not None:
            return self._cache

        raw = self._read_yaml()
        source_section = raw.get("source", {})

        # 解析 csv_source
        csv_section = source_section.get("csv_source", {})
        csv_enc_list = csv_section.get("encoding_fallbacks")
        if csv_enc_list is None:
            raise ValueError("缺少 source.csv_source.encoding_fallbacks 配置项")
        csv_encoding_fallbacks = tuple(csv_enc_list)
        csv_batch_rows = csv_section.get("batch_rows")
        if csv_batch_rows is None:
            raise ValueError("缺少 source.csv_source.batch_rows 配置项")

        # 解析 xlsx_source
        xlsx_section = source_section.get("xlsx_source", {})
        xlsx_batch_rows = xlsx_section.get("batch_rows")
        if xlsx_batch_rows is None:
            raise ValueError("缺少 source.xlsx_source.batch_rows 配置项")

        text_section = source_section.get("text_source", {})

        # 解析 extensions 为 set
        ext_list = text_section.get("extensions", [])
        extensions = set(ext_list) if ext_list else set()

        # 解析 encoding_fallbacks 为 tuple
        enc_list = text_section.get("encoding_fallbacks", [])
        encoding_fallbacks = tuple(enc_list) if enc_list else tuple()

        # 解析 pre_chunk
        pre_chunk_section = text_section.get("pre_chunk", {})
        boundaries_raw = pre_chunk_section.get("boundaries", [])
        boundaries = tuple(boundaries_raw) if boundaries_raw else tuple()
        pre_chunk = PreChunkConfig(
            enabled=pre_chunk_section.get("enabled", True),
            chunk_chars=pre_chunk_section.get("chunk_chars", 500),
            boundaries=boundaries,
        )

        # 解析 markdown_source
        md_section = source_section.get("markdown_source", {})
        md_enc_list = md_section.get("encoding_fallbacks", [])
        md_encoding_fallbacks = tuple(md_enc_list) if md_enc_list else tuple()
        md_pre_chunk_section = md_section.get("pre_chunk", [])
        md_boundaries_raw = md_pre_chunk_section.get("boundaries", [])
        md_boundaries = tuple(md_boundaries_raw) if md_boundaries_raw else tuple()
        md_pre_chunk = PreChunkConfig(
            chunk_chars=md_pre_chunk_section.get("chunk_chars", 800),
            boundaries=md_boundaries,
        )

        # 解析 doc_source
        doc_section = source_section.get("doc_source", {})
        if not doc_section:
            raise ValueError("缺少 source.doc_source 配置项")
        doc_pre_chunk_section = doc_section.get("pre_chunk", {})
        if not doc_pre_chunk_section:
            raise ValueError("缺少 source.doc_source.pre_chunk 配置项")
        doc_boundaries_raw = doc_pre_chunk_section.get("boundaries", [])
        doc_boundaries = tuple(doc_boundaries_raw) if doc_boundaries_raw else tuple()
        doc_pre_chunk = PreChunkConfig(
            enabled=doc_pre_chunk_section.get("enabled", True),
            chunk_chars=doc_pre_chunk_section.get("chunk_chars", 600),
            boundaries=doc_boundaries,
        )
        doc_include_tables = doc_section.get("include_tables")
        if doc_include_tables is None:
            raise ValueError("缺少 source.doc_source.include_tables 配置项")

        # 解析 pptx_source
        pptx_section = source_section.get("pptx_source", {})
        if not pptx_section:
            raise ValueError("缺少 source.pptx_source 配置项")
        pptx_pre_chunk_section = pptx_section.get("pre_chunk", {})
        if not pptx_pre_chunk_section:
            raise ValueError("缺少 source.pptx_source.pre_chunk 配置项")
        pptx_boundaries_raw = pptx_pre_chunk_section.get("boundaries", [])
        pptx_boundaries = tuple(pptx_boundaries_raw) if pptx_boundaries_raw else tuple()
        pptx_pre_chunk = PreChunkConfig(
            enabled=pptx_pre_chunk_section.get("enabled", True),
            chunk_chars=pptx_pre_chunk_section.get("chunk_chars", 500),
            boundaries=pptx_boundaries,
        )
        pptx_include_tables = pptx_section.get("include_tables")
        if pptx_include_tables is None:
            raise ValueError("缺少 source.pptx_source.include_tables 配置项")
        pptx_include_notes = pptx_section.get("include_notes")
        if pptx_include_notes is None:
            raise ValueError("缺少 source.pptx_source.include_notes 配置项")
        pptx_extract_images = pptx_section.get("extract_images")
        if pptx_extract_images is None:
            raise ValueError("缺少 source.pptx_source.extract_images 配置项")

        # 解析 html_source
        html_section = source_section.get("html_source", {})
        if not html_section:
            raise ValueError("缺少 source.html_source 配置项")
        html_enc_list = html_section.get("encoding_fallbacks")
        if html_enc_list is None:
            raise ValueError("缺少 source.html_source.encoding_fallbacks 配置项")
        html_encoding_fallbacks = tuple(html_enc_list)
        html_pre_chunk_section = html_section.get("pre_chunk", {})
        if not html_pre_chunk_section:
            raise ValueError("缺少 source.html_source.pre_chunk 配置项")
        html_boundaries_raw = html_pre_chunk_section.get("boundaries", [])
        html_boundaries = tuple(html_boundaries_raw) if html_boundaries_raw else tuple()
        html_pre_chunk = PreChunkConfig(
            enabled=html_pre_chunk_section.get("enabled", True),
            chunk_chars=html_pre_chunk_section.get("chunk_chars", 800),
            boundaries=html_boundaries,
        )
        html_include_links = html_section.get("include_links")
        if html_include_links is None:
            raise ValueError("缺少 source.html_source.include_links 配置项")
        html_include_tables = html_section.get("include_tables")
        if html_include_tables is None:
            raise ValueError("缺少 source.html_source.include_tables 配置项")

        self._cache = SourceConfig(
            csv_source=CsvSourceConfig(
                encoding_fallbacks=csv_encoding_fallbacks,
                batch_rows=csv_batch_rows,
            ),
            xlsx_source=XlsxSourceConfig(
                batch_rows=xlsx_batch_rows,
            ),
            text_source=TextSourceConfig(
                extensions=extensions,
                encoding_fallbacks=encoding_fallbacks,
                pre_chunk=pre_chunk,
            ),
            markdown_source=MarkdownSourceConfig(
                encoding_fallbacks=md_encoding_fallbacks,
                pre_chunk=md_pre_chunk,
            ),
            doc_source=DocSourceConfig(
                pre_chunk=doc_pre_chunk,
                include_tables=doc_include_tables,
            ),
            pptx_source=PptxSourceConfig(
                pre_chunk=pptx_pre_chunk,
                include_tables=pptx_include_tables,
                include_notes=pptx_include_notes,
                extract_images=pptx_extract_images,
            ),
            html_source=HtmlSourceConfig(
                encoding_fallbacks=html_encoding_fallbacks,
                pre_chunk=html_pre_chunk,
                include_links=html_include_links,
                include_tables=html_include_tables,
            ),
        )
        return self._cache

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"数据源配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or not isinstance(raw_cfg, dict):
            raise ValueError("数据源配置文件格式错误：需要顶层键值对")
        return raw_cfg
