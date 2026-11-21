# app-server/src/com/damon/ming/ai/rag/summary/summary_segmenter.py
"""摘要输入分段与上下文重叠处理。"""

import re
from dataclasses import dataclass
from math import floor

from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer


@dataclass(frozen=True)
class SummarySegment:
    """摘要主体文本及仅供理解的前文上下文。"""

    content: str
    context: str = ""


class SummarySegmenter:
    """按文档结构拆分摘要输入，并为跨片段内容添加有限上下文。"""

    def __init__(
        self,
        tokenizer: BaseTokenizer,
        context_message_template: str,
        context_overlap_ratio: float | None,
    ):
        self.tokenizer = tokenizer
        self.context_message_template = context_message_template
        self.context_overlap_ratio = context_overlap_ratio or 0.0

    def split(self, text: str, max_input_tokens: int) -> list[SummarySegment]:
        """按输入预算切分，并给同章节续片添加句子或表格表头上下文。"""
        context_prefix = self.context_message_template.replace(
            "{context}", "", 1
        ).replace("{content}", "", 1)
        context_label_tokens = self.tokenizer.count_tokens(context_prefix)
        overlap_budget = floor(max_input_tokens * self.context_overlap_ratio)
        if (
            overlap_budget > 0
            and max_input_tokens > overlap_budget + context_label_tokens
        ):
            core_segment_size = max_input_tokens - overlap_budget - context_label_tokens
        else:
            overlap_budget = 0
            core_segment_size = max_input_tokens

        core_segments = self._split_text_preserving_boundaries(text, core_segment_size)
        segments = self._attach_overlap_context(
            core_segments, overlap_budget, max_input_tokens
        )
        return segments

    def build_context_message(self, content: str, context: str) -> str:
        return self.context_message_template.replace("{context}", context, 1).replace(
            "{content}", content, 1
        )

    def _attach_overlap_context(
        self,
        segments: list[str],
        overlap_budget: int,
        max_segment_tokens: int,
    ) -> list[SummarySegment]:
        """仅在同章节边界带入前一句；表格续片则带入表头和分隔行。"""
        result: list[SummarySegment] = []
        for index, content in enumerate(segments):
            context = ""
            if index > 0 and overlap_budget > 0:
                context = self._select_overlap_context(
                    segments[index - 1], content, overlap_budget
                )
                if (
                    context
                    and self.tokenizer.count_tokens(
                        self.build_context_message(content, context)
                    )
                    > max_segment_tokens
                ):
                    context = ""
            result.append(SummarySegment(content=content, context=context))
        return result

    def _select_overlap_context(
        self, previous: str, current: str, max_context_tokens: int
    ) -> str:
        current_body = self._remove_section_heading(current)
        current_lines = current_body.splitlines()
        if current_lines and self._is_table_row(current_lines[0]):
            table_header = self._table_header_from_previous(previous)
            if (
                table_header
                and self.tokenizer.count_tokens(table_header) <= max_context_tokens
            ):
                return table_header

        previous_heading = self._section_heading(previous)
        current_heading = self._section_heading(current)
        if previous.rstrip().endswith("---"):
            return ""
        if previous_heading != current_heading and (
            previous_heading is not None or current_heading is not None
        ):
            return ""

        sentence = self._last_complete_sentence(previous)
        if sentence and self.tokenizer.count_tokens(sentence) <= max_context_tokens:
            return sentence
        return ""

    @staticmethod
    def _section_heading(text: str) -> str | None:
        match = re.match(r"^(【[^\r\n]+】)(?:\r?\n)?", text)
        return match.group(1) if match else None

    @classmethod
    def _remove_section_heading(cls, text: str) -> str:
        match = re.match(r"^(【[^\r\n]+】(?:\r?\n)?)", text)
        return text[len(match.group(1)) :] if match else text

    @staticmethod
    def _table_header_from_previous(text: str) -> str:
        lines = text.rstrip().splitlines()
        table_start = len(lines)
        while table_start > 0 and SummarySegmenter._is_table_row(
            lines[table_start - 1]
        ):
            table_start -= 1
        table_lines = lines[table_start:]
        if (
            len(table_lines) >= 2
            and SummarySegmenter._is_table_row(table_lines[0])
            and SummarySegmenter._is_table_row(table_lines[1])
            and re.search(r"-{3,}", table_lines[1])
        ):
            return "\n".join(table_lines[:2])
        return ""

    @staticmethod
    def _is_table_row(line: str) -> bool:
        return "|" in line

    @staticmethod
    def _last_complete_sentence(text: str) -> str:
        text = text.rstrip()
        if text.endswith("---"):
            return ""
        if text.splitlines() and SummarySegmenter._is_table_row(text.splitlines()[-1]):
            return ""
        text = SummarySegmenter._remove_section_heading(text).rstrip()
        endings = list(
            re.finditer(
                r"[。！？!?]+(?:[”’」』】）》\"']*)|"
                r"[.]+(?:[”’」』】）》\"']*)(?=\s|$)",
                text,
            )
        )
        if not endings:
            return ""
        sentence_start = endings[-2].end() if len(endings) > 1 else 0
        return text[sentence_start : endings[-1].end()].strip()

    def _split_text_preserving_boundaries(
        self, text: str, max_tokens_per_segment: int
    ) -> list[str]:
        """优先按章节、段落和句子拆分，始终从原文切片以保留字符。"""
        if max_tokens_per_segment <= 0:
            raise ValueError("分段 token 上限必须大于 0")
        if self.tokenizer.count_tokens(text) <= max_tokens_per_segment:
            return [text]

        segments: list[str] = []
        current = ""
        for section in self._split_sections(text):
            if self.tokenizer.count_tokens(section) <= max_tokens_per_segment:
                if (
                    current
                    and self.tokenizer.count_tokens(current + section)
                    > max_tokens_per_segment
                ):
                    segments.append(current)
                    current = ""
                current += section
                continue

            if current:
                segments.append(current)
                current = ""

            heading_match = re.match(r"^(【[^\r\n]+】(?:\r?\n)?)", section)
            heading = heading_match.group(1) if heading_match else ""
            if (
                heading
                and self.tokenizer.count_tokens(heading) < max_tokens_per_segment
            ):
                body_segments = self._split_natural_text(
                    section[len(heading) :],
                    max_tokens_per_segment - self.tokenizer.count_tokens(heading),
                )
                segments.extend(heading + body for body in body_segments)
            else:
                segments.extend(
                    self._split_natural_text(section, max_tokens_per_segment)
                )

        if current:
            segments.append(current)
        return segments

    @staticmethod
    def _split_sections(text: str) -> list[str]:
        """按重构阶段使用的章节分隔符切分，并将分隔符保留在前一节。"""
        sections: list[str] = []
        start = 0
        for match in re.finditer(r"\n---\n", text):
            sections.append(text[start : match.end()])
            start = match.end()
        if start < len(text):
            sections.append(text[start:])
        return sections or [text]

    def _split_natural_text(self, text: str, max_tokens: int) -> list[str]:
        """按换行和句末标点拆分，超长句再按词和 Unicode 字符细分。"""
        boundaries = re.finditer(
            r"(?:\r?\n)+|[。！？!?]+(?:[”’」』】）》\"']*)|"
            r"[.]+(?:[”’」』】）》\"']*)(?=\s|$)",
            text,
        )
        units: list[str] = []
        start = 0
        for boundary in boundaries:
            end = boundary.end()
            if end > start:
                units.append(text[start:end])
                start = end
        if start < len(text):
            units.append(text[start:])
        return self._pack_units(units or [text], max_tokens)

    def _pack_units(self, units: list[str], max_tokens: int) -> list[str]:
        segments: list[str] = []
        current = ""
        for unit in units:
            if self.tokenizer.count_tokens(unit) > max_tokens:
                if current:
                    segments.append(current)
                    current = ""
                segments.extend(self._split_long_unit(unit, max_tokens))
            elif current and self.tokenizer.count_tokens(current + unit) > max_tokens:
                segments.append(current)
                current = unit
            else:
                current += unit
        if current:
            segments.append(current)
        return segments

    def _split_long_unit(self, text: str, max_tokens: int) -> list[str]:
        """先按空白边界切分，单个超长词再按 Unicode 字符安全切分。"""
        pieces = re.findall(r"\s+|\S+", text)
        if not pieces:
            return [text]

        segments: list[str] = []
        current = ""
        for piece in pieces:
            if self.tokenizer.count_tokens(piece) > max_tokens:
                if current:
                    segments.append(current)
                    current = ""
                segments.extend(self._split_by_characters(piece, max_tokens))
            elif current and self.tokenizer.count_tokens(current + piece) > max_tokens:
                segments.append(current)
                current = piece
            else:
                current += piece
        if current:
            segments.append(current)
        return segments

    def _split_by_characters(self, text: str, max_tokens: int) -> list[str]:
        """在原始字符串上找 token 预算内的 Unicode 字符切片，不做 token decode。"""
        segments: list[str] = []
        start = 0
        while start < len(text):
            low, high = start + 1, len(text)
            best_end = start
            while low <= high:
                middle = (low + high) // 2
                if self.tokenizer.count_tokens(text[start:middle]) <= max_tokens:
                    best_end = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best_end == start:
                # 单个字符也可能超过极小预算；保留字符完整性并让后端错误走既有兜底。
                best_end = start + 1
            segments.append(text[start:best_end])
            start = best_end
        return segments
