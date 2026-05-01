"""Gemini 2.5 Flash 기반 의류 bbox 탐지 + 얼굴 영역 추출."""
import asyncio
import json
import logging
import os
import re

from PIL import Image, ImageFilter
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

VALID_LABELS = {
    'face',
    'top_outer', 'top_inner', 'outer', 'bottom', 'dress',
    'shoes', 'bag',
    'accessory_ring', 'accessory_necklace', 'accessory_earring',
    'accessory_belt', 'accessory_hat', 'accessory_watch',
}


class BoundingBox(BaseModel):
    label: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 1.0

    @field_validator('label')
    @classmethod
    def validate_label(cls, v: str) -> str:
        v_lower = v.lower().strip()
        if v_lower == 'top':
            return 'top_outer'
        if v_lower not in VALID_LABELS:
            logger.warning("[BoundingBox] 알 수 없는 레이블: %s", v)
        return v_lower


class DetectionResult(BaseModel):
    boxes: list[BoundingBox]


_DETECTION_PROMPT = """
이미지에서 사람의 얼굴과 모든 의류/액세서리 영역을 빠짐없이 탐지하라.
각 영역을 bounding box(정수 좌표, 0~1000 정규화)로 반환한다.

탐지 가능한 레이블 (해당하는 모든 영역 반환, 같은 레이블도 여러 개 OK):
- face (얼굴)
- top_outer (위에 걸친 셔츠/카디건/재킷 등 외곽 상의 — 단추 열려있거나 안에 다른 옷 보이면 outer)
- top_inner (안쪽 상의 — 티셔츠/탱크탑/크롭탑/이너용 셔츠. 위에 다른 옷 걸쳐도 보이면 분리 탐지)
- outer (코트/패딩/점퍼 — 두꺼운 겉옷)
- bottom (바지/스커트/반바지)
- dress (원피스/점프수트)
- shoes (신발)
- bag (가방/숄더백/토트백/크로스백)
- accessory_ring (반지)
- accessory_necklace (목걸이/펜던트)
- accessory_earring (귀걸이)
- accessory_belt (벨트)
- accessory_hat (모자/베레모/캡)
- accessory_watch (시계)

규칙:
- 레이어드 코디(셔츠 안에 티셔츠)는 top_outer + top_inner로 둘 다 탐지
- 액세서리는 작아도 보이면 반드시 탐지
- 같은 레이블도 시각적으로 다른 영역이면 여러 개 반환 (예: 양쪽 귀걸이)
- 의류가 없는 영역은 포함하지 않음
- confidence는 탐지 확신도 0.0~1.0

JSON 형식으로만 응답:
{"boxes": [{"label": "top_inner", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "confidence": 0.9}]}
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
