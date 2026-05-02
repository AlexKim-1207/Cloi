"""EasyOCR로 자막/UI 텍스트 감지 + 블러 마스킹.

paddlepaddle Python 3.11 wheel 불안정 → EasyOCR (PyTorch 기반).
"""
from typing import List
import numpy as np
from PIL import Image, ImageFilter

_reader = None


def _load() -> None:
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)


def detect_text_boxes(img: Image.Image) -> List[List[int]]:
    _load()
    assert _reader is not None
    arr = np.array(img)
    results = _reader.readtext(arr, detail=1)
    boxes: List[List[int]] = []
    for bbox, *_ in results:
        xs = [int(p[0]) for p in bbox]
        ys = [int(p[1]) for p in bbox]
        boxes.append([min(xs), min(ys), max(xs), max(ys)])
    return boxes


def blur_boxes(img: Image.Image, boxes: List[List[int]], radius: int = 18) -> Image.Image:
    out = img.copy()
    for x1, y1, x2, y2 in boxes:
        region = out.crop((x1, y1, x2, y2))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=radius))
        out.paste(blurred, (x1, y1))
    return out
