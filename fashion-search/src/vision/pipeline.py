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
        loop = asyncio.get_event_loop()

        # 1. DINO: bbox 감지 (CPU 집약)
        bboxes = await loop.run_in_executor(
            None, detect_garments, tmp_path, text_prompt, 0.30
        )
        if not bboxes:
            logger.warning("[vision_pipeline] 의류 감지 실패 (bbox 없음)")
            return []

        # 2. SAM2: 세그멘테이션 → crop
        crops = await loop.run_in_executor(
            None, segment_from_bbox, tmp_path, bboxes,
            settings.gemini_confidence_threshold,
        )
        return crops

    except Exception as exc:
        logger.error("[vision_pipeline] 파이프라인 오류: %s", exc)
        return []

    finally:
        os.unlink(tmp_path)
