# app-server/src/com/damon/ming/ai/source/pptx_data_source.py
"""
PPTX 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

使用 python-pptx 提取 PPT 文件的文本、表格、备注内容。

工业级特性：
  - 按幻灯片分页，每页一个 Document（slide 文本 + speaker notes）
  - 表格提取：Word/PPT 内嵌表格格式化为 Markdown 表格
  - 图片提取：幻灯片内嵌图片 OCR 后追加到当页文本
  - 预分块：超大文本按自然边界切分

可配置项通过 SourceConfigLoader 从 YAML 读取：
  - pptx_source.pre_chunk: 预分块配置
  - pptx_source.include_tables: 是否提取表格
  - pptx_source.include_notes: 是否提取演讲者备注
  - pptx_source.extract_images: 是否提取图片并 OCR

page 语义：每张幻灯片 = 一"页"，page_index 按幻灯片顺序递增。
"""

import hashlib
import os
import threading
from pathlib import Path

from llama_index.core import Document
from pptx import Presentation
from src.com.damon.ming.ai.config.source.source_config_loader import SourceConfigLoader
from src.com.damon.ming.ai.source import register_engine
from src.com.damon.ming.ai.source.base import BaseDataSource
from src.com.damon.ming.log import pin

logger = pin("LocalPptxDataSource")


@register_engine("pptx")
class LocalPptxDataSource(BaseDataSource):
    """PPTX 文件加载实现，同步处理。

    上层 RAGContainer 使用 asyncio.to_thread 或 ThreadPoolExecutor
    将本类的调用提交到线程池，本类不感知线程环境。
    """

    def __init__(
        self,
        folder_path: str,
        pre_chunk_config=None,
        include_tables: bool | None = None,
        include_notes: bool | None = None,
        extract_images: bool | None = None,
        vlm_model: str | None = None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalPptxDataSource")
        self._ensure_dir_exists()
        self._images_dir = os.path.join(folder_path, "images")
        self.vlm_model = vlm_model

        cfg = SourceConfigLoader().load()
        self._pre_chunk_config = (
            pre_chunk_config
            if pre_chunk_config is not None
            else cfg.pptx_source.pre_chunk
        )
        self._include_tables = (
            include_tables
            if include_tables is not None
            else cfg.pptx_source.include_tables
        )
        self._include_notes = (
            include_notes
            if include_notes is not None
            else cfg.pptx_source.include_notes
        )
        self._extract_images = (
            extract_images
            if extract_images is not None
            else cfg.pptx_source.extract_images
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
            "total_notes": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[PptxDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    @staticmethod
    def _extract_text_from_shapes(shapes) -> list[str]:
        """从幻灯片形状中提取文本（文本框、占位符等）。"""
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        texts: list[str] = []
        for shape in shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        texts.append(text)
            # 递归处理组合形状（group shapes）
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                sub_texts = LocalPptxDataSource._extract_text_from_shapes(shape.shapes)
                texts.extend(sub_texts)
        return texts

    @staticmethod
    def _extract_tables_from_shapes(shapes) -> list[str]:
        """从幻灯片形状中提取表格，格式化为 Markdown 表格。"""
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        tables: list[str] = []
        for shape in shapes:
            if shape.has_table:
                table = shape.table
                rows: list[list[str]] = []
                for row in table.rows:
                    cells = [
                        cell.text.strip().replace("|", "\\|") for cell in row.cells
                    ]
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

            # 递归处理组合形状（group shapes）
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                sub_tables = LocalPptxDataSource._extract_tables_from_shapes(
                    shape.shapes
                )
                tables.extend(sub_tables)

        return tables

    def _extract_images_from_slide(
        self, slide, output_dir: str, slide_idx: int, file_stem: str
    ) -> tuple[list[str], list[str]]:
        """从幻灯片中提取图片，OCR 返回文本列表和路径列表。

        python-pptx 不直接提供图片提取接口，
        通过遍历 slide 的 XML 找 <a:blip> 元素获取图片 rId，
        再从 package 中提取原始字节。
        """
        image_paths: list[str] = []
        image_texts: list[str] = []

        try:
            from src.com.damon.ming.ai.source.image_text_extractor import (
                extract_image_text,
            )

            # 遍历 slide XML 找所有图片关系 ID
            blip_embeds: list[str] = []
            for elem in slide._element.iter():
                # <a:blip r:embed="rId2">
                for attr_name, attr_value in elem.attrib.items():
                    if "embed" in attr_name and attr_value:
                        blip_embeds.append(attr_value)

            if not blip_embeds:
                return image_texts, image_paths

            Path(output_dir).mkdir(parents=True, exist_ok=True)

            for img_idx, r_id in enumerate(blip_embeds):
                try:
                    image_part = slide.part.related_parts.get(r_id)
                    if image_part is None:
                        continue

                    image_bytes = image_part.blob
                    content_type = (
                        image_part.content_type
                        if hasattr(image_part, "content_type")
                        else ""
                    )

                    # 根据 content_type 推断扩展名
                    ext = "png"
                    if "jpeg" in content_type or "jpg" in content_type:
                        ext = "jpg"
                    elif "png" in content_type:
                        ext = "png"
                    elif "gif" in content_type:
                        ext = "gif"
                    elif "emf" in content_type:
                        ext = "emf"
                    elif "wmf" in content_type:
                        ext = "wmf"

                    image_filename = (
                        f"{file_stem}_slide{slide_idx + 1}_img{img_idx + 1}.{ext}"
                    )
                    image_path = str(Path(output_dir) / image_filename)

                    with open(image_path, "wb") as f:
                        f.write(image_bytes)

                    image_paths.append(image_path)

                    # OCR
                    img_text = extract_image_text(image_path, self.vlm_model)
                    if img_text:
                        image_texts.append(img_text)

                except Exception as e:
                    self.logger.debug(
                        f"[PptxDataSource] 图片提取失败 slide{slide_idx + 1} img{img_idx + 1}: {e!s}"
                    )
                    continue

        except Exception as e:
            self.logger.exception(
                f"[PptxDataSource] 图片提取失败 slide{slide_idx + 1}: {e!s}"
            )

        return image_texts, image_paths

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
        """处理单个 PPTX 文件"""
        file_name = os.path.basename(file_path)
        suffix = Path(file_path).suffix.lower()

        try:
            file_sha256 = self._get_file_sha256(file_path)

            if suffix in (".ppt",):
                self.logger.warning(
                    f"[PptxDataSource] 跳过旧版 .ppt 文件（请先转为 .pptx）: {file_name}"
                )
                return []

            prs = Presentation(file_path)

            if not prs.slides:
                self.logger.warning(f"[PptxDataSource] 空演示文稿: {file_name}")
                return []

            docs: list[Document] = []
            global_page_index = 0
            total_notes_count = 0

            for slide_idx, slide in enumerate(prs.slides):
                # 提取幻灯片文本
                shape_texts = self._extract_text_from_shapes(slide.shapes)
                slide_text = "\n".join(shape_texts)

                # 提取备注
                notes_text = ""
                if self._include_notes and slide.has_notes_slide:
                    notes_slide = slide.notes_slide
                    notes_texts = self._extract_text_from_shapes(notes_slide.shapes)
                    notes_text = "\n".join(notes_texts)
                    if notes_text.strip():
                        total_notes_count += 1

                # 提取表格
                table_texts: list[str] = []
                if self._include_tables:
                    table_texts = self._extract_tables_from_shapes(slide.shapes)

                # 提取图片 + OCR
                image_texts: list[str] = []
                all_image_paths: list[str] = []
                if self._extract_images:
                    file_stem = Path(file_path).stem
                    image_texts, all_image_paths = self._extract_images_from_slide(
                        slide, self._images_dir, slide_idx, file_stem
                    )

                # 合并页面文本
                full_text = slide_text
                if notes_text:
                    full_text += f"\n\n[备注]\n{notes_text}"
                for tbl in table_texts:
                    full_text += f"\n\n{tbl}"
                for img_txt in image_texts:
                    full_text += f"\n\n{img_txt}"

                full_text = full_text.strip()
                if not full_text:
                    continue

                # 预分块
                sub_texts = self._pre_chunk_text(full_text)

                for chunk_text in sub_texts:
                    doc = Document(
                        text=chunk_text,
                        metadata={
                            "file_name": file_name,
                            "file_path": file_path,
                            "file_sha256": file_sha256,
                            "source_refId": file_sha256,
                            "page": global_page_index + 1,
                            "page_index": global_page_index,
                            "slide_index": slide_idx,
                            "images": all_image_paths,
                            "has_notes": bool(notes_text.strip()),
                        },
                    )
                    docs.append(doc)
                    global_page_index += 1

            total_pages = global_page_index
            # 回填 total_pages
            for doc in docs:
                doc.metadata["total_pages"] = total_pages

            # 更新统计
            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_pages"] += total_pages
                self._stats["total_tables"] += 0  # 表格已合并到文本
                self._stats["total_notes"] += total_notes_count

            self.logger.info(
                f"[PptxDataSource] 读取成功 | file={file_name} | "
                f"slides={len(prs.slides)} | pages={total_pages} | "
                f"notes={total_notes_count} | sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[PptxDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 PPTX 文件（同步）"""
        self.logger.info(f"[PptxDataSource] 开始加载目录: {self.folder_path}")

        pptx_files = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith((".pptx", ".ppt")):
                    pptx_files.append(os.path.abspath(os.path.join(root, fname)))

        if not pptx_files:
            self.logger.warning(
                f"[PptxDataSource] 目录中没有 PPTX 文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(pptx_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_pages": 0,
                    "total_tables": 0,
                    "total_notes": 0,
                }

        all_docs = []
        for file_path in pptx_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[PptxDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总备注={self._stats['total_notes']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的 PPTX 文件列表，用于增量上传（同步）"""
        self.logger.info(f"[PptxDataSource] 增量加载指定文件 count={len(file_paths)}")

        pptx_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() in (".pptx", ".ppt"):
                pptx_files.append(str(p))
            else:
                self.logger.warning(f"[PptxDataSource] 跳过非PPTX/不存在文件: {fp}")

        if not pptx_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(pptx_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_pages": 0,
                    "total_tables": 0,
                    "total_notes": 0,
                }

        all_docs = []
        for file_path in pptx_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[PptxDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总备注={self._stats['total_notes']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
