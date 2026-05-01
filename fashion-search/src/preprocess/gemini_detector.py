"""Gemini 2.5 Flash 기반 의류 bbox 탐지 + 얼굴 영역 추출."""
import asyncio
import json
import logging
import os
import re

from PIL import Image, ImageFilter
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BoundingBox(BaseModel):
    label: str  # 'face', 'top', 'outer', 'bottom', 'shoes', 'bag', etc.
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 1.0


class DetectionResult(BaseModel):
    boxes: list[BoundingBox]


_DETECTION_PROMPT = """
이미지 속 다음 영역들의 bounding box를 정수 좌표(0~1000 정규화)로 반환하라:
- face (얼굴)
- top, outer, bottom, dress (의류)
- shoes, bag (잡화)

JSON 형식으로만 응답:
{"boxes": [{"label": "face", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "confidence": 0.9}]}

의류가 없는 영역은 포함하지 않는다. 각 레이블당 1개만.
"""

_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


def _parse_detection_response(text: str) -> DetectionResult:
    """Gemini 응답 텍스트에서 JSON 파싱. 실패 시 빈 결과."""
    try:
        m = _JSON_RE.search(text)
        if not m:
            return DetectionResult(boxes=[])
        data = json.loads(m.group())
        return DetectionResult(**data)
    except Exception as exc:
        logger.warning("[gemini_detector] 응답 파싱 실패: %s", exc)
        return DetectionResult(boxes=[])


async def detect_regions(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> DetectionResult:
    """Gemini 2.5 Flash로 의류/얼굴 bbox 추출.

    좌표는 0~1000 정규화 → 실제 픽셀 변환은 호출자 책임.
    """
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            logger.warning("[gemini_detector] GOOGLE_API_KEY 미설정")
            return DetectionResult(boxes=[])

        client = genai.Client(api_key=api_key)

        def _call() -> str:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    _DETECTION_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            return resp.text or ""

        raw_text = await asyncio.to_thread(_call)
        return _parse_detection_response(raw_text)

    except Exception as exc:
        logger.warning("[gemini_detector] detect_regions 실패: %s", exc)
        return DetectionResult(boxes=[])


def blur_face_regions(image: Image.Image, boxes: list[BoundingBox]) -> Image.Image:
    """얼굴 영역만 블러 처리 (개인정보 보호 + 임베딩 노이즈 감소)."""
    out = image.copy()
    w, h = image.size
    for box in boxes:
        if box.label != 'face':
            continue
        x1 = int(box.x1 * w / 1000)
        y1 = int(box.y1 * h / 1000)
        x2 = int(box.x2 * w / 1000)
        y2 = int(box.y2 * h / 1000)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = out.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(radius=20))
        out.paste(crop, (x1, y1))
    return out


def crop_garment_regions(
    image: Image.Image,
    boxes: list[BoundingBox],
    expand_ratio: float = 0.08,
) -> dict[str, Image.Image]:
    """의류별 crop 이미지 dict 반환. 레이블 → PIL Image."""
    w, h = image.size
    crops: dict[str, Image.Image] = {}
    for box in boxes:
        if box.label == 'face':
            continue
        x1 = int(box.x1 * w / 1000)
        y1 = int(box.y1 * h / 1000)
        x2 = int(box.x2 * w / 1000)
        y2 = int(box.y2 * h / 1000)
        if x2 <= x1 or y2 <= y1:
            continue
        dx = int((x2 - x1) * expand_ratio)
        dy = int((y2 - y1) * expand_ratio)
        x1 = max(0, x1 - dx)
        y1 = max(0, y1 - dy)
        x2 = min(w, x2 + dx)
        y2 = min(h, y2 + dy)
        crops[box.label] = image.crop((x1, y1, x2, y2))
    return crops
