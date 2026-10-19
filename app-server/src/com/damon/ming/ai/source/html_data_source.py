# app-server/src/com/damon/ming/ai/source/html_data_source.py
"""
HTML 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

使用 BeautifulSoup (lxml) 解析 HTML 文件，提取正文内容。

工业级特性：
  - 智能正文提取：移除 script/style/nav/footer/aside 等非内容元素，
    优先从 article/main/role=main 等语义标签提取正文
  - 标题层级保留：识别 h1~h6，将标题层级写入 metadata
  - 链接保留：将超链接文本和 URL 组合为 "文本 (URL)" 格式
  - 表格提取：HTML 表格格式化为 Markdown 表格
  - 预分块：超大正文按自然边界切分

可配置项通过 SourceConfigLoader 从 YAML 读取：
  - html_source.encoding_fallbacks: 编码尝试顺序
  - html_source.pre_chunk: 预分块配置
  - html_source.include_links: 是否保留超链接 URL
  - html_source.include_tables: 是否提取 HTML 表格

page 语义：整个 HTML 文件为一页，超大正文按 pre_chunk 切分后 page_index 递增。
"""

import hashlib
import os
import threading
from pathlib import Path

from bs4 import BeautifulSoup, Comment, Tag
from llama_index.core import Document
from src.com.damon.ming.ai.config.source.source_config_loader import SourceConfigLoader
from src.com.damon.ming.ai.source import register_engine
from src.com.damon.ming.ai.source.base import BaseDataSource
from src.com.damon.ming.log import pin

logger = pin("LocalHtmlDataSource")

# 非内容标签：解析时直接移除
_NON_CONTENT_TAGS = frozenset([
    "script", "style", "noscript", "iframe", "svg", "canvas",
    "nav", "footer", "header", "aside", "menu",
])

# 正文容器选择器（按优先级）
_CONTENT_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    ".content",
    "#content",
    ".article",
    "#article",
    ".post",
    "#post",
]

# 标题标签
_HEADING_TAGS = frozenset(["h1", "h2", "h3", "h4", "h5", "h6"])


@register_engine("html")
class LocalHtmlDataSource(BaseDataSource):
    """HTML 文件加载实现，同步处理。

    上层 RAGContainer 使用 asyncio.to_thread 或 ThreadPoolExecutor
    将本类的调用提交到线程池，本类不感知线程环境。
    """

    def __init__(
        self,
        folder_path: str,
        encoding_fallbacks: tuple[str, ...] | None = None,
        pre_chunk_config=None,
        include_links: bool | None = None,
        include_tables: bool | None = None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalHtmlDataSource")
        self._ensure_dir_exists()

        cfg = SourceConfigLoader().load()
        self._encoding_fallbacks = (
            encoding_fallbacks if encoding_fallbacks is not None else cfg.html_source.encoding_fallbacks
        )
        self._pre_chunk_config = (
            pre_chunk_config if pre_chunk_config is not None else cfg.html_source.pre_chunk
        )
        self._include_links = (
            include_links if include_links is not None else cfg.html_source.include_links
        )
        self._include_tables = (
            include_tables if include_tables is not None else cfg.html_source.include_tables
        )

        # 实例级别锁
        self._stats_lock = threading.Lock()

        # 统计信息（线程安全）
        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
            "total_pages": 0,
            "total_tables": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[HtmlDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _read_html_file(self, file_path: str) -> str:
        """读取 HTML 文件，按编码链尝试。"""
        for encoding in self._encoding_fallbacks:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        # 兜底：utf-8 忽略错误
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @staticmethod
    def _remove_non_content_elements(soup: BeautifulSoup) -> None:
        """移除非内容元素（script, style, nav, footer 等）。"""
        for tag_name in _NON_CONTENT_TAGS:
            for elem in soup.find_all(tag_name):
                elem.decompose()

        # 移除 HTML 注释
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()

    @staticmethod
    def _extract_main_content(soup: BeautifulSoup) -> Tag:
        """智能提取正文容器。

        优先从语义标签查找，否则回退到 body。
        """
        for selector in _CONTENT_SELECTORS:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                return elem

        # 回退到 body
        if soup.body:
            return soup.body

        return soup

    def _extract_tables_from_soup(self, content_elem: Tag) -> list[str]:
        """从 HTML 元素中提取表格，格式化为 Markdown 表格。"""
        tables: list[str] = []
        for table_elem in content_elem.find_all("table"):
            rows: list[list[str]] = []

            # 处理 thead
            thead = table_elem.find("thead")
            if thead:
                for tr in thead.find_all("tr"):
                    cells = [
                        td.get_text(strip=True).replace("|", "\\|")
                        for td in tr.find_all(["th", "td"])
                    ]
                    if cells:
                        rows.append(cells)

            # 处理 tbody 或直接 tr
            tbody = table_elem.find("tbody") or table_elem
            for tr in tbody.find_all("tr"):
                cells = [
                    td.get_text(strip=True).replace("|", "\\|")
                    for td in tr.find_all(["th", "td"])
                ]
                if cells:
                    rows.append(cells)

            if not rows:
                continue

            col_count = max(len(r) for r in rows)
            for r in rows:
                while len(r) < col_count:
                    r.append("")

            lines = []
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("| " + " | ".join(["---"] * col_count) + " |")
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")

            tables.append("\n".join(lines))

        return tables

    def _element_to_text(self, elem: Tag) -> tuple[str, int | None]:
        """将 HTML 元素转为结构化文本。

        Returns:
            (text, heading_level)
            heading_level 为 None 表示非标题，1-6 表示 h1~h6。
        """
        lines: list[str] = []
        min_heading: int | None = None

        for child in elem.descendants:
            if not isinstance(child, Tag):
                continue

            # 跳过已处理的子元素
            if child.name in _NON_CONTENT_TAGS:
                continue

            # 标题
            if child.name in _HEADING_TAGS:
                level = int(child.name[1])
                text = child.get_text(strip=True)
                if text:
                    prefix = "#".ljust(level + 1, "#")  # "## " / "### "
                    lines.append(f"\n{prefix}{text}\n")
                    if min_heading is None or level < min_heading:
                        min_heading = level
                continue

            # 段落
            if child.name == "p":
                text = self._extract_paragraph_text(child)
                if text:
                    lines.append(text)
                continue

            # 列表
            if child.name in ("ul", "ol"):
                list_text = self._extract_list_text(child)
                if list_text:
                    lines.append(list_text)
                continue

            # div/section 等块级元素 — 只取其直接文本（避免重复）
            if child.name in ("div", "section", "span"):
                # 如果该元素没有块级子元素，取其文本
                has_block_child = any(
                    isinstance(c, Tag) and c.name in (
                        "p", "div", "section", "ul", "ol", "table",
                        "h1", "h2", "h3", "h4", "h5", "h6",
                        "article", "main",
                    )
                    for c in child.children
                )
                if not has_block_child:
                    text = child.get_text(strip=True)
                    if text:
                        lines.append(text)

        return "\n".join(lines).strip(), min_heading

    def _extract_paragraph_text(self, para: Tag) -> str:
        """提取段落文本，处理内联链接。"""
        parts: list[str] = []
        for child in para.descendants:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    parts.append(text)
            elif isinstance(child, Tag):
                if child.name == "a" and self._include_links:
                    href = child.get("href", "")
                    text = child.get_text(strip=True)
                    if text:
                        if href and href not in ("#", "javascript:void(0)"):
                            parts.append(f"{text} ({href})")
                        else:
                            parts.append(text)
                elif child.name == "img":
                    alt = child.get("alt", "").strip()
                    if alt:
                        parts.append(f"[图片: {alt}]")
                elif child.name == "br":
                    parts.append("\n")

        return "".join(parts).strip()

    def _extract_list_text(self, list_elem: Tag) -> str:
        """提取列表文本。"""
        items: list[str] = []
        for li in list_elem.find_all("li", recursive=False):
            # 排除嵌套列表中的 li
            if li.parent != list_elem:
                continue
            text = li.get_text(strip=True).replace("|", "\\|")
            if text:
                items.append(f"- {text}")

        return "\n".join(items)

    def _pre_chunk_text(self, text: str) -> list[str]:
        """按配置的自然边界优先级预分块。"""
        cfg = self._pre_chunk_config
        if not cfg.enabled or len(text) <= cfg.chunk_chars:
            return [text]

        chunk_size = cfg.chunk_chars
        boundaries = cfg.boundaries

        chunks: list[str] = []
        pos = 0
        text_len = len(text)

        while pos < text_len:
            end = min(pos + chunk_size, text_len)

            if end < text_len:
                split_pos = self._find_split_pos(text, pos, end, boundaries)
                end = split_pos

            chunks.append(text[pos:end])

            if end >= text_len:
                break

            pos = end

        return [c for c in chunks if c.strip()]

    @staticmethod
    def _find_split_pos(
        text: str, start: int, end: int, boundaries: tuple[str, ...]
    ) -> int:
        """在 [start, end] 范围内找最佳切分点。"""
        mid = start + (end - start) // 2

        for sep in boundaries:
            if sep == "":
                return end

            search_region = text[mid:end]
            last_idx = search_region.rfind(sep)
            if last_idx != -1:
                return mid + last_idx + len(sep)

        return end

    def _process_single_file(self, file_path: str) -> list[Document]:
        """处理单个 HTML 文件"""
        file_name = os.path.basename(file_path)

        try:
            file_sha256 = self._get_file_sha256(file_path)
            html_content = self._read_html_file(file_path)

            if not html_content.strip():
                self.logger.warning(f"[HtmlDataSource] 空文件: {file_name}")
                return []

            # 解析 HTML
            soup = BeautifulSoup(html_content, "lxml")

            # 移除非内容元素
            self._remove_non_content_elements(soup)

            # 提取正文容器
            content_elem = self._extract_main_content(soup)

            # 提取正文文本
            main_text, heading_level = self._element_to_text(content_elem)

            if not main_text:
                self.logger.warning(f"[HtmlDataSource] 无正文内容: {file_name}")
                return []

            # 提取表格
            table_texts: list[str] = []
            if self._include_tables:
                table_texts = self._extract_tables_from_soup(content_elem)

            # 合并文本
            full_text = main_text
            for tbl in table_texts:
                full_text += f"\n\n{tbl}"

            full_text = full_text.strip()
            if not full_text:
                return []

            # 预分块
            sub_texts = self._pre_chunk_text(full_text)

            docs: list[Document] = []
            for idx, chunk_text in enumerate(sub_texts):
                doc = Document(
                    text=chunk_text,
                    metadata={
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_sha256": file_sha256,
                        "source_refId": file_sha256,
                        "page": idx + 1,
                        "page_index": idx,
                        "heading_level": heading_level,
                    },
                )
                docs.append(doc)

            total_pages = len(docs)
            for doc in docs:
                doc.metadata["total_pages"] = total_pages

            # 更新统计
            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_pages"] += total_pages
                self._stats["total_tables"] += len(table_texts)

            self.logger.info(
                f"[HtmlDataSource] 读取成功 | file={file_name} | "
                f"pages={total_pages} | tables={len(table_texts)} | "
                f"sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[HtmlDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 HTML 文件（同步）"""
        self.logger.info(f"[HtmlDataSource] 开始加载目录: {self.folder_path}")

        html_files = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith((".html", ".htm")):
                    html_files.append(os.path.abspath(os.path.join(root, fname)))

        if not html_files:
            self.logger.warning(
                f"[HtmlDataSource] 目录中没有 HTML 文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(html_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_pages": 0,
                    "total_tables": 0,
                }

        all_docs = []
        for file_path in html_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[HtmlDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总表格={self._stats['total_tables']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的 HTML 文件列表，用于增量上传（同步）"""
        self.logger.info(f"[HtmlDataSource] 增量加载指定文件 count={len(file_paths)}")

        html_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() in (".html", ".htm"):
                html_files.append(str(p))
            else:
                self.logger.warning(f"[HtmlDataSource] 跳过非HTML/不存在文件: {fp}")

        if not html_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(html_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_pages": 0,
                    "total_tables": 0,
                }

        all_docs = []
        for file_path in html_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[HtmlDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总表格={self._stats['total_tables']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
