"""SAM 2 기반 의류 세그멘테이션.

segment-anything-2 PyPI 패키지 사용 (git clone 방식 아님).
pip install segment-anything-2==1.0.0
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from src.config.settings import get_settings
from .detect_gdino import BBox

logger = logging.getLogger(__name__)


@dataclass
class GarmentCrop:
    crop_image: Image.Image
    category_hint: str
    confidence: float
    bbox: BBox
    needs_gemini: bool = field(default=False)  # confidence < threshold 시 Gemini fallback


_sam2_predictor = None


def _load_predictor():
    global _sam2_predictor
    if _sam2_predictor is not None:
        return _sam2_predictor

    settings = get_settings()
    try:
        from sam2.build_sam import build_sam2  # type: ignore
        from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore

        sam2 = build_sam2(settings.sam2_model_cfg, settings.sam2_checkpoint)
        _sam2_predictor = SAM2ImagePredictor(sam2)
        logger.info("[segment_sam2] SAM 2 predictor 로드 완료")
    except ImportError:
        logger.error("[segment_sam2] segment-anything-2 패키지가 없습니다. pip install segment-anything-2==1.0.0")
        raise
    return _sam2_predictor


def segment_from_bbox(
    image_path: str | Path,
    bboxes: list[BBox],
    gemini_confidence_threshold: float | None = None,
) -> list[GarmentCrop]:
    """bbox 리스트로부터 garment crop PNG 생성.

    Args:
        image_path: 원본 이미지 경로
        bboxes: detect_garments()에서 반환된 BBox 리스트
        gemini_confidence_threshold: 이 값 미만이면 GarmentCrop.needs_gemini=True

    Returns:
        GarmentCrop 리스트
    """
    if not bboxes:
        return []

    settings = get_settings()
    threshold = gemini_confidence_threshold or settings.gemini_confidence_threshold

    predictor = _load_predictor()
    image = Image.open(image_path).convert("RGB")
    image_np = np.array(image)

    predictor.set_image(image_np)

    crops: list[GarmentCrop] = []
    for bbox in bboxes:
        try:
            input_box = np.array([[bbox.x1, bbox.y1, bbox.x2, bbox.y2]])
            masks, scores, _ = predictor.predict(
                point_coords=None,
                point_labels=None,
                box=input_box,
                multimask_output=False,
            )
            mask = masks[0].astype(bool)
            crop = _mask_to_crop(image, mask, bbox)
            crops.append(
                GarmentCrop(
                    crop_image=crop,
                    category_hint=bbox.label,
                    confidence=float(scores[0]),
                    bbox=bbox,
                    needs_gemini=float(scores[0]) < threshold,
                )
            )
        except Exception as exc:
            logger.warning("[segment_sam2] bbox 세그멘테이션 실패: %s", exc)

    logger.info("[segment_sam2] %d개 crop 생성 완료", len(crops))
    return crops


def _mask_to_crop(image: Image.Image, mask: np.ndarray, bbox: BBox) -> Image.Image:
    """마스크 영역을 bbox로 crop하고 배경을 흰색으로 처리."""
    rgba = image.convert("RGBA")
    img_np = np.array(rgba)
    img_np[~mask, 3] = 0  # 마스크 바깥 투명
    result = Image.fromarray(img_np, "RGBA")

    x1, y1, x2, y2 = int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)
    cropped = result.crop((x1, y1, x2, y2))

    # 흰 배경에 합성
    bg = Image.new("RGB", cropped.size, (255, 255, 255))
    bg.paste(cropped, mask=cropped.split()[3])
    return bg
