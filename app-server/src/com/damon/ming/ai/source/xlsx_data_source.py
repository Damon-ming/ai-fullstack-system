# app-server/src/com/damon/ming/ai/source/xlsx_data_source.py
"""
Excel (XLSX) 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

与 CSV 数据源的核心差异：
  - 多 sheet 支持：每个 sheet 独立生成一组 Document（page_index 跨 sheet 递增）
  - 依赖 openpyxl 引擎（pandas read_excel 底层）
  - 空单元格自动填充为空字符串
  - 公式结果读取缓存值（openpyxl 的 data_only=True）

page 语义：每个 sheet 的每个 batch = 一"页"，sheet_name 写入 metadata。
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

logger = pin("LocalXlsxDataSource")


@register_engine("xlsx")
class LocalXlsxDataSource(BaseDataSource):
    """Excel (XLSX) 数据源，按 sheet × 行分批打包为 Document。"""

    def __init__(
        self,
        folder_path: str,
        batch_rows: int | None = None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalXlsxDataSource")
        self._ensure_dir_exists()

        if batch_rows is None:
            cfg = SourceConfigLoader().load()
            self._batch_rows = cfg.xlsx_source.batch_rows
        else:
            self._batch_rows = batch_rows

        # 实例级别锁
        self._stats_lock = threading.Lock()

        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
            "total_rows": 0,
            "total_sheets": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[XlsxDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _read_sheets(self, file_path: str) -> dict[str, pd.DataFrame]:
        """读取所有 sheet，返回 {sheet_name: DataFrame}。

        data_only=True 读取公式缓存值而非公式字符串。
        """
        try:
            sheets = pd.read_excel(
                file_path,
                sheet_name=None,  # 读取全部 sheet
                engine="openpyxl",
                dtype=str,  # 全部按字符串处理，避免类型推断破坏数据
                na_values=[],  # 不自动转换空值为 NaN
            )
            return {name: df for name, df in sheets.items() if not df.empty}
        except Exception:
            self.logger.exception(f"[XlsxDataSource] 读取 Excel 失败: {file_path}")
            return {}

    def _format_as_table(self, df: pd.DataFrame) -> str:
        """DataFrame → Markdown 表格。"""
        if df.empty:
            return ""

        df_clean = df.fillna("")
        headers = [str(h) for h in df_clean.columns]
        col_count = len(headers)

        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for _, row in df_clean.iterrows():
            lines.append("| " + " | ".join(str(v) for v in row) + " |")

        return "\n".join(lines)

    def _process_single_file(self, file_path: str) -> list[Document]:
        """处理单个 XLSX 文件"""
        file_name = os.path.basename(file_path)

        try:
            file_sha256 = self._get_file_sha256(file_path)
            sheets = self._read_sheets(file_path)

            if not sheets:
                self.logger.warning(
                    f"[XlsxDataSource] 空文件/无有效 sheet: {file_name}"
                )
                return []

            docs: list[Document] = []
            global_page_index = 0
            total_rows_all = 0

            for sheet_name, df in sheets.items():
                sheet_rows = len(df)
                total_rows_all += sheet_rows

                # 分批
                batches: list[pd.DataFrame] = []
                for i in range(0, sheet_rows, self._batch_rows):
                    batches.append(df.iloc[i : i + self._batch_rows])

                for batch_df in batches:
                    table_text = self._format_as_table(batch_df)
                    if not table_text:
                        continue

                    row_start = (
                        global_page_index // len(batches) if batches else 0
                    ) * self._batch_rows + 1
                    row_end = row_start + len(batch_df) - 1

                    doc = Document(
                        text=table_text,
                        metadata={
                            "file_name": file_name,
                            "file_path": file_path,
                            "file_sha256": file_sha256,
                            "source_refId": file_sha256,
                            "page": global_page_index + 1,
                            "page_index": global_page_index,
                            "row_start": row_start,
                            "row_end": row_end,
                            "sheet_name": sheet_name,
                        },
                    )
                    docs.append(doc)
                    global_page_index += 1

            total_pages = global_page_index
            # 回填 total_pages
            for doc in docs:
                doc.metadata["total_pages"] = total_pages

            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_rows"] += total_rows_all
                self._stats["total_sheets"] += len(sheets)

            self.logger.info(
                f"[XlsxDataSource] 读取成功 | file={file_name} | "
                f"sheets={len(sheets)} | rows={total_rows_all} | "
                f"batches={total_pages} | sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[XlsxDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 XLSX 文件（同步）"""
        self.logger.info(f"[XlsxDataSource] 开始加载目录: {self.folder_path}")

        xlsx_files = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith((".xlsx", ".xls")):
                    xlsx_files.append(os.path.abspath(os.path.join(root, fname)))

        if not xlsx_files:
            self.logger.warning(
                f"[XlsxDataSource] 目录中没有 Excel 文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(xlsx_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_rows": 0,
                    "total_sheets": 0,
                }

        all_docs = []
        for file_path in xlsx_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[XlsxDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"sheets={self._stats['total_sheets']} | "
                f"总行数={self._stats['total_rows']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的 XLSX 文件列表，用于增量上传（同步）"""
        self.logger.info(f"[XlsxDataSource] 增量加载指定文件 count={len(file_paths)}")
        xlsx_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() in (".xlsx", ".xls"):
                xlsx_files.append(str(p))
            else:
                self.logger.warning(f"[XlsxDataSource] 跳过非Excel/不存在文件: {fp}")

        if not xlsx_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(xlsx_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_rows": 0,
                    "total_sheets": 0,
                }

        all_docs = []
        for file_path in xlsx_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[XlsxDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"sheets={self._stats['total_sheets']} | "
                f"总行数={self._stats['total_rows']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
