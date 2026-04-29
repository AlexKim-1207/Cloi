"""Vision 파이프라인 — detect + segment 통합 (async)."""
import asyncio
import io
import logging
from pathlib import Path

from PIL import Image

from src.config.settings import get_settings
from .detect_gdino import detect_garments, DEFAULT_TEXT_PROMPT
from .segment_sam2 import segment_from_bbox, GarmentCrop

logger = logging.getLogger(__name__)


async def run_vision_pipeline(
    image_bytes: bytes,
    text_prompt: str = DEFAULT_TEXT_PROMPT,
) -> list[GarmentCrop]:
    """이미지 바이트 → GarmentCrop 리스트 (비동기).

    CPU 집약 작업이므로 executor로 오프로드.

    Args:
        image_bytes: 업로드된 원본 이미지 bytes
        text_prompt: DINO 감지 텍스트 프롬프트

    Returns:
        GarmentCrop 리스트 (빈 리스트이면 감지 실패)
    """
    settings = get_settings()

    # 이미지 임시 저장 (DINO / SAM2가 파일 경로를 요구)
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        # 전체 이미지를 하나의 crop으로 처리 (DINO/SAM2 Python 3.13 호환성 이슈로 폴백 고정)
        from .detect_gdino import BBox
        from .segment_sam2 import GarmentCrop
        full_image = Image.open(tmp_path).convert("RGB")
        w, h = full_image.size
        fallback_bbox = BBox(x1=0, y1=0, x2=w, y2=h, label="clothing", confidence=1.0)
        fallback_crop = GarmentCrop(
            crop_image=full_image,
            category_hint="clothing",
            confidence=1.0,
            bbox=fallback_bbox,
            needs_gemini=True,
        )
        logger.info("[vision_pipeline] 전체 이미지 임베딩 모드")
        return [fallback_crop]

    except Exception as exc:
        logger.error("[vision_pipeline] 파이프라인 오류: %s", exc)
        return []

    finally:
        os.unlink(tmp_path)
