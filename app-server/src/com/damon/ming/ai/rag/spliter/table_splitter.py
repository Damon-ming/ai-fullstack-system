# app-server/src/com/damon/ming/ai/rag/spliter/table_splitter.py
"""Markdown 表格检测与表格感知切分。"""

import re
from collections.abc import Callable

from llama_index.core import Document
from llama_index.core.node_parser import TokenTextSplitter
from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import (
    CONTENT_TYPE,
    RECONSTRUCTION_SKIP_CHARS,
)

_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


class TableAwareSplitter:
    """在保留表格边界与表头的情况下切分 Markdown 文本。"""

    def __init__(self, count_tokens: Callable[[str], int]) -> None:
        self._count_tokens = count_tokens

    def find_table_blocks(self, text: str) -> list[tuple[int, int]]:
        """检测文本中的所有 markdown 表格区域，返回 [(start, end), ...]。

        表格定义：连续的行，首行为表头行（| col | col |），
        第二行为分隔行（|---|---|），后续为数据行。
        表格前后的空行视为表格的一部分（作为间隔）。
        """
        lines = text.split("\n")
        blocks: list[tuple[int, int]] = []
        i = 0
        n = len(lines)

        while i < n - 1:
            # 找表头行：当前行是 |...|，下一行是 |---|---|
            if _TABLE_ROW_RE.match(lines[i]) and _TABLE_SEP_RE.match(lines[i + 1]):
                # 找到表格起点：向前吞并一个空行
                start_line = i
                if i > 0 and lines[i - 1].strip() == "":
                    start_line = i - 1

                # 向后找表格结束：连续的 |...| 行
                j = i + 2
                while j < n and _TABLE_ROW_RE.match(lines[j]):
                    j += 1

                # 表格在原文中的字符偏移
                char_start = sum(len(lines[k]) + 1 for k in range(start_line))
                char_end = sum(len(lines[k]) + 1 for k in range(j))
                char_end = min(char_end, len(text))

                blocks.append((char_start, char_end))
                i = j
            else:
                i += 1

        return blocks

    def _split_table_with_header(
        self, table_text: str, limit: int
    ) -> list[tuple[str, int]]:
        """将超大表格按行切分，每个子表格都带表头行。

        例如 100 行数据的大表会被拆为多个子表，每个子表都包含
        表头行和分隔行，确保每个 chunk 语义完整可读。
        """
        lines = [l for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 3:
            return [(table_text, 0)]  # 不够表头+分隔+一行数据，不拆

        header = lines[0]
        separator = lines[1]
        data_rows = lines[2:]
        header_block = f"{header}\n{separator}"
        header_tokens = self._count_tokens(header_block)

        chunks: list[tuple[str, int]] = []
        current_rows: list[str] = []
        current_tokens = header_tokens

        for row in data_rows:
            row_tokens = self._count_tokens(row)
            if current_tokens + row_tokens > limit and current_rows:
                # 当前批次已满，组装一个子表格
                chunks.append(
                    (
                        f"{header_block}\n" + "\n".join(current_rows),
                        0 if not chunks else len(header_block) + 1,
                    )
                )
                current_rows = [row]
                current_tokens = header_tokens + row_tokens
            else:
                current_rows.append(row)
                current_tokens += row_tokens

        if current_rows:
            chunks.append(
                (
                    f"{header_block}\n" + "\n".join(current_rows),
                    0 if not chunks else len(header_block) + 1,
                )
            )

        return chunks

    def split(
        self,
        text: str,
        table_blocks: list[tuple[int, int]],
        limit: int,
        token_splitter: TokenTextSplitter,
    ) -> list[TextNode]:
        """表格感知的章节分割。

        普通文本段独立切分，表格段按原位置插入；超大表格按行切分并重复表头。
        """
        # 按原文顺序划分普通文本和表格区域
        segments: list[tuple[int, int, bool]] = []  # (start, end, is_table)
        cursor = 0
        for tb_start, tb_end in table_blocks:
            if tb_start > cursor:
                segments.append((cursor, tb_start, False))
            segments.append((tb_start, tb_end, True))
            cursor = tb_end
        if cursor < len(text):
            segments.append((cursor, len(text), False))

        result_nodes: list[TextNode] = []
        for start, end, is_table in segments:
            segment_text = text[start:end]
            if not segment_text.strip():
                continue
            if not is_table:
                for node in token_splitter.get_nodes_from_documents(
                    [Document(text=segment_text)]
                ):
                    node.start_char_idx = start + (node.start_char_idx or 0)
                    node.end_char_idx = start + (node.end_char_idx or len(node.text))
                    result_nodes.append(node)
                continue

            if self._count_tokens(segment_text) <= limit:
                table_chunks = [(segment_text, 0)]
            else:
                table_chunks = self._split_table_with_header(segment_text, limit)
            for table_text, skip_chars in table_chunks:
                table_node = TextNode(text=table_text)
                table_node.start_char_idx = start
                table_node.end_char_idx = end
                table_node.metadata[CONTENT_TYPE] = "table"
                table_node.metadata[RECONSTRUCTION_SKIP_CHARS] = skip_chars
                result_nodes.append(table_node)

        return result_nodes if result_nodes else [TextNode(text=text)]
