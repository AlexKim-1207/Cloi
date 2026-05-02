"""PaddleOCR 한국어 OCR로 자막/UI 텍스트 마스킹.

보고서 추천: PP-OCRv5 multilingual (106개 언어 지원)
"""
from typing import List
import numpy as np
from PIL import Image, ImageFilter

_ocr = None


def _load():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(lang="korean", use_angle_cls=True, show_log=False)


def detect_text_boxes(img: Image.Image) -> List[List[int]]:
    _load()
    ocr_engine = _ocr
    assert ocr_engine is not None
    arr = np.array(img)
    result = ocr_engine.predict(arr)  # PP-OCRv5 API
    boxes: List[List[int]] = []
    for item in result or []:
        det_res = item.get("dt_polys") or []
        for poly in det_res:
            xs = [int(p[0]) for p in poly]
            ys = [int(p[1]) for p in poly]
            boxes.append([min(xs), min(ys), max(xs), max(ys)])
    return boxes


def blur_boxes(img: Image.Image, boxes: List[List[int]], radius: int = 18) -> Image.Image:
    out = img.copy()
    for x1, y1, x2, y2 in boxes:
        region = out.crop((x1, y1, x2, y2))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=radius))
        out.paste(blurred, (x1, y1))
    return out
