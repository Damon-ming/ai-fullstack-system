# app-server/src/com/damon/ming/ai/source/csv_data_source.py
"""
CSV 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

CSV 无"页"概念，因此：
  - 将整个 CSV 按 batch_rows 分批，每批生成一个 Document
  - 每个 Document 视为一"页"：page_index 递增，page = page_index + 1
  - 表格以 Markdown 表格式文本输出，保留列头信息
  - metadata 携带 row_start / row_end 用于原始行号回溯

与 PDF/MD 的 page 语义对齐：
  - splitter 按 page_index 排序合并 → CSV 多 batch 按顺序拼接
  - section_id = section_{file_sha256}_{text_hash}，与格式无关
  - chunk_id = chunk_{file_sha256}_{text_hash}，与格式无关
"""

import hashlib
import os
import threading
from pathlib import Path

import pandas as pd
from llama_index.core import Document
from src.com.damon.ming.ai.config.source.source_config_loader import SourceConfigLoader
from src.com.damon.ming.ai.source import register_engine
from src.com.damon.ming.ai.source.base import BaseDataSource
from src.com.damon.ming.log import pin

logger = pin("LocalCsvDataSource")


@register_engine("csv")
class LocalCsvDataSource(BaseDataSource):
    """CSV 数据源，按行分批打包为 Document。"""

    # 每个 Document 包含的行数（不含表头）
    DEFAULT_BATCH_ROWS = 50

    def __init__(
        self,
        folder_path: str,
        encoding_fallbacks: tuple[str, ...] | None = None,
        batch_rows: int | None = None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalCsvDataSource")
        self._ensure_dir_exists()

        # 从 YAML 加载配置
        if encoding_fallbacks is None or batch_rows is None:
            cfg = SourceConfigLoader().load()
            self._encoding_fallbacks = (
                encoding_fallbacks
                if encoding_fallbacks is not None
                else cfg.csv_source.encoding_fallbacks
            )
            self._batch_rows = (
                batch_rows if batch_rows is not None else cfg.csv_source.batch_rows
            )
        else:
            self._encoding_fallbacks = encoding_fallbacks
            self._batch_rows = batch_rows

        # 实例级别锁
        self._stats_lock = threading.Lock()

        # 统计信息（线程安全）
        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
            "total_rows": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[CsvDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _read_csv(self, file_path: str) -> pd.DataFrame:
        """用 pandas 读取 CSV，按编码顺序尝试。

        pandas 自动处理：引号转义、换行字段、BOM、不规则列数、空值。
        """
        for encoding in self._encoding_fallbacks:
            try:
                df = pd.read_csv(file_path, encoding=encoding, dtype=str)
                if df.empty:
                    return pd.DataFrame()
                return df
            except (UnicodeDecodeError, LookupError):
                continue

        # 兜底：utf-8 + errors=ignore
        df = pd.read_csv(
            file_path, encoding="utf-8", encoding_errors="ignore", dtype=str
        )
        return df if not df.empty else pd.DataFrame()

    def _format_as_table(self, df: pd.DataFrame) -> str:
        """将 DataFrame 批次格式化为 Markdown 表格文本。

        pandas to_markdown 自动处理列对齐、缺失值。
        下游检索时能利用列头信息提升匹配精度。
        """
        if df.empty:
            return ""

        # 将 NaN 替换为空字符串，确保文本干净
        df_clean = df.fillna("")

        lines = []
        headers = list(df_clean.columns)
        col_count = len(headers)

        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for _, row in df_clean.iterrows():
            lines.append("| " + " | ".join(str(v) for v in row) + " |")

        return "\n".join(lines)

    def _process_single_file(self, file_path: str) -> list[Document]:
        """处理单个 CSV 文件"""
        file_name = os.path.basename(file_path)

        try:
            file_sha256 = self._get_file_sha256(file_path)
            df = self._read_csv(file_path)

            if df.empty:
                self.logger.warning(f"[CsvDataSource] 空文件: {file_name}")
                return []

            total_rows = len(df)

            # 分批
            batches: list[pd.DataFrame] = []
            for i in range(0, total_rows, self._batch_rows):
                batches.append(df.iloc[i : i + self._batch_rows])

            total_pages = len(batches)
            docs = []
            for page_index, batch_df in enumerate(batches):
                table_text = self._format_as_table(batch_df)
                if not table_text:
                    continue

                row_start = page_index * self._batch_rows + 1
                row_end = row_start + len(batch_df) - 1

                doc = Document(
                    text=table_text,
                    metadata={
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_sha256": file_sha256,
                        "source_refId": file_sha256,
                        # 与 PDF/MD 对齐：每个 batch = 一"页"
                        "page": page_index + 1,
                        "page_index": page_index,
                        "total_pages": total_pages,
                        # CSV 特有：原始行号回溯
                        "row_start": row_start,
                        "row_end": row_end,
                    },
                )
                docs.append(doc)

            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_rows"] += total_rows

            self.logger.info(
                f"[CsvDataSource] 读取成功 | file={file_name} | "
                f"rows={total_rows} | batches={total_pages} | "
                f"sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[CsvDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 CSV 文件（同步）"""
        self.logger.info(f"[CsvDataSource] 开始加载目录: {self.folder_path}")

        csv_files = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith(".csv"):
                    csv_files.append(os.path.abspath(os.path.join(root, fname)))

        if not csv_files:
            self.logger.warning(
                f"[CsvDataSource] 目录中没有 CSV 文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(csv_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0
                self._stats["total_rows"] = 0

        all_docs = []
        for file_path in csv_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[CsvDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总行数={self._stats['total_rows']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的 CSV 文件列表，用于增量上传（同步）"""
        self.logger.info(f"[CsvDataSource] 增量加载指定文件 count={len(file_paths)}")
        csv_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() == ".csv":
                csv_files.append(str(p))
            else:
                self.logger.warning(f"[CsvDataSource] 跳过非CSV/不存在文件: {fp}")

        if not csv_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(csv_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0
                self._stats["total_rows"] = 0

        all_docs = []
        for file_path in csv_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[CsvDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总行数={self._stats['total_rows']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
