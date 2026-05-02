"""얼굴 검출 + 블러 마스킹 (개인정보 보호 + 임베딩 노이즈 감소)."""
from typing import List
import cv2
import numpy as np
from PIL import Image, ImageFilter

_cascade = None


def _load():
    global _cascade
    if _cascade is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]
        _cascade = cv2.CascadeClassifier(cascade_path)


def detect_faces(img: Image.Image) -> List[List[int]]:
    _load()
    cascade = _cascade
    assert cascade is not None
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
    if len(faces) == 0:
        return []
    return [[int(x), int(y), int(x + w), int(y + h)] for (x, y, w, h) in faces]


def blur_faces(img: Image.Image, boxes: List[List[int]], radius: int = 24) -> Image.Image:
    out = img.copy()
    for x1, y1, x2, y2 in boxes:
        region = out.crop((x1, y1, x2, y2))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=radius))
        out.paste(blurred, (x1, y1))
    return out
