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
class SourceConfig:
    """数据源总配置（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。"""

    # 文本数据源配置
    text_source: TextSourceConfig = field(default_factory=TextSourceConfig)


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

        self._cache = SourceConfig(
            text_source=TextSourceConfig(
                extensions=extensions,
                encoding_fallbacks=encoding_fallbacks,
                pre_chunk=pre_chunk,
            )
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
