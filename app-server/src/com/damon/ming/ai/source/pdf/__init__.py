# app-server/src/com/damon/ming/ai/source/pdf/__init__.py
"""
PDF 解析策略层 —— 多策略解析 + 路由。

路由规则：
    1. PDF 有可选中文字 → TextPdfParser（pymupdf4llm 快速路径）
    2. PDF 无可选中文字（纯图片） → ScannedPdfParser（PaddleOCR 路径）

新增策略：
    1. 继承 BasePdfParser，实现 parse()
    2. 在 route_pdf_parser() 中加一条规则
"""

import fitz
from src.com.damon.ming.ai.source.pdf.base_pdf import BasePdfParser
from src.com.damon.ming.ai.source.pdf.scanned_pdf import ScannedPdfParser
from src.com.damon.ming.ai.source.pdf.text_pdf import TextPdfParser

# 有可选中文字时，文字占比超过此阈值走文本路径
_TEXT_RATIO_THRESHOLD = 0.5


def route_pdf_parser(
    file_path: str,
    images_dir: str,
    enable_image_extract: bool = False,
    vlm_model: str | None = None,
) -> BasePdfParser:
    """根据 PDF 特征路由到对应的解析器。

    检测逻辑：
      - 采样前 5 页，计算文字字符数 / 页面面积
      - 超过阈值 → 文本 PDF
      - 否则 → 扫描件 PDF

    新增解析策略只需在此函数中追加 elif 分支。
    """
    if _has_selectable_text(file_path):
        return TextPdfParser(
            images_dir=images_dir,
            enable_image_extract=enable_image_extract,
            vlm_model=vlm_model,
        )
    return ScannedPdfParser(
        images_dir=images_dir,
        vlm_model=vlm_model,
    )


def _has_selectable_text(file_path: str) -> bool:
    """检测 PDF 是否有可选中文字层。

    采样前 5 页，检查每页提取的文字是否超过阈值。
    """
    try:
        doc = fitz.open(file_path)
        sample_pages = min(5, doc.page_count)
        if sample_pages == 0:
            doc.close()
            return False

        text_chars = 0
        for i in range(sample_pages):
            page = doc[i]
            text = page.get_text()
            text_chars += len(text.strip())

        doc.close()
        # 平均每页至少 50 个字符才算有可选中文字
        avg_chars_per_page = text_chars / sample_pages
        return avg_chars_per_page > 50

    except Exception:
        return False


__all__ = [
    "BasePdfParser",
    "ScannedPdfParser",
    "TextPdfParser",
    "route_pdf_parser",
]
