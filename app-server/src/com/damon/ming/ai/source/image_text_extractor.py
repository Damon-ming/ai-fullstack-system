# app-server/src/com/damon/ming/ai/source/image_text_extractor.py
"""
文档图片文本提取器 —— OCR + VLM 混合策略。

处理文档内嵌图片：
  1. 优先用 PaddleOCR 提取图片中的文字
  2. 若 OCR 结果过少（纯图表/流程图/照片），降级到 VLM 生成描述
  3. 两者结合返回可检索的纯文本

设计约束：
  - PaddleOCR 模型加载为类级别单例，避免重复加载
  - Ollama VLM 使用同步客户端（数据源运行在线程池中）
  - 所有方法均为同步接口，适配 ThreadPoolExecutor 环境
"""

import base64
import threading
from pathlib import Path

import fitz  # pymupdf
import ollama
from paddleocr import PaddleOCR
from src.com.damon.ming.log import pin

logger = pin("ImageTextExtractor")

# 类级别锁，保证 PaddleOCR 单例线程安全
_ocr_lock = threading.Lock()
_ocr_instance: PaddleOCR | None = None

# VLM 降级阈值：OCR 文字少于此值时启用 VLM
VLM_FALLBACK_THRESHOLD = 20


def _get_ocr() -> PaddleOCR:
    """获取 PaddleOCR 单例（懒加载，线程安全）。"""
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                logger.info("[ImageTextExtractor] 初始化 PaddleOCR...")
                _ocr_instance = PaddleOCR(
                    use_angle_cls=True,
                    lang="ch",  # 中英文混合
                    show_log=False,
                )
                logger.info("[ImageTextExtractor] PaddleOCR 初始化完成")
    return _ocr_instance


def extract_image_text(image_path: str, vlm_model: str | None = None) -> str:
    """从图片中提取可检索文本。

    策略：
      1. PaddleOCR 提取文字
      2. 若 OCR 文字少于阈值且配置了 VLM，用 VLM 生成描述补充

    Args:
        image_path: 图片文件路径。
        vlm_model: VLM 模型名（None 则不启用 VLM 降级）。

    Returns:
        提取的文本，无内容时返回空字符串。
    """
    ocr_text = _ocr_extract(image_path)

    if len(ocr_text.strip()) < VLM_FALLBACK_THRESHOLD and vlm_model:
        vlm_text = _vlm_describe(image_path, vlm_model)
        if vlm_text:
            return vlm_text

    return ocr_text


def _ocr_extract(image_path: str) -> str:
    """PaddleOCR 提取图片文字。"""
    try:
        ocr = _get_ocr()
        result = ocr.ocr(image_path, cls=True)

        if not result or not result[0]:
            return ""

        lines: list[str] = []
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0] if line[1] else ""
                if text:
                    lines.append(text)

        return "\n".join(lines)

    except Exception as e:
        logger.exception(f"[ImageTextExtractor] OCR 失败: {image_path} | error={e!s}")
        return ""


def _vlm_describe(image_path: str, model_name: str) -> str:
    """VLM 生成图片描述。"""
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        response = ollama.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": "请用中文描述这张图片的内容，包括所有可见的文字、数据、图表信息。",
                    "images": [b64_image],
                }
            ],
            options={"temperature": 0.1},
        )

        return response.get("message", {}).get("content", "").strip()

    except Exception as e:
        logger.exception(
            f"[ImageTextExtractor] VLM 描述失败: {image_path} | model={model_name} | error={e!s}"
        )
        return ""


def extract_images_from_pdf_page(
    pdf_path: str, page_no: int, output_dir: str
) -> list[str]:
    """从 PDF 指定页面提取图片，保存到磁盘。

    Args:
        pdf_path: PDF 文件路径。
        page_no: 页码（0-based）。
        output_dir: 图片保存目录。

    Returns:
        保存的图片文件路径列表。
    """
    image_paths: list[str] = []
    try:
        doc = fitz.open(pdf_path)
        if page_no >= doc.page_count:
            doc.close()
            return []

        page = doc[page_no]
        images = page.get_images(full=True)

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            if not base_image:
                continue

            image_bytes = base_image["image"]
            ext = base_image.get("ext", "png")

            # 文件名：{pdf_sha256[:8]}_page{page_no+1}_img{idx+1}.ext
            pdf_name = Path(pdf_path).stem
            image_filename = f"{pdf_name}_page{page_no + 1}_img{img_idx + 1}.{ext}"
            image_path = str(Path(output_dir) / image_filename)

            with open(image_path, "wb") as f:
                f.write(image_bytes)

            image_paths.append(image_path)

        doc.close()

    except Exception as e:
        logger.exception(
            f"[ImageTextExtractor] PDF 图片提取失败: {pdf_path} p{page_no + 1} | error={e!s}"
        )

    return image_paths


def extract_images_from_docx(docx_path: str, output_dir: str) -> list[str]:
    """从 DOCX 文件中提取所有图片，保存到磁盘。

    Args:
        docx_path: DOCX 文件路径。
        output_dir: 图片保存目录。

    Returns:
        保存的图片文件路径列表。
    """
    image_paths: list[str] = []
    try:
        # DOCX 是 ZIP，图片存储在 word/media/ 目录
        import zipfile

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        docx_name = Path(docx_path).stem

        with zipfile.ZipFile(docx_path, "r") as zf:
            media_files = [f for f in zf.namelist() if f.startswith("word/media/")]

            for media_file in media_files:
                image_bytes = zf.read(media_file)
                ext = Path(media_file).suffix.lstrip(".")
                if not ext:
                    ext = "png"

                media_name = Path(media_file).stem
                image_filename = f"{docx_name}_{media_name}.{ext}"
                image_path = str(Path(output_dir) / image_filename)

                with open(image_path, "wb") as f:
                    f.write(image_bytes)

                image_paths.append(image_path)

    except Exception as e:
        logger.exception(
            f"[ImageTextExtractor] DOCX 图片提取失败: {docx_path} | error={e!s}"
        )

    return image_paths
