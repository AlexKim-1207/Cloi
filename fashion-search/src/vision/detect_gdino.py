"""Grounding DINO 기반 의류 감지.

groundingdino-unofficial PyPI 패키지 사용 (git clone 방식 아님).
pip install groundingdino-unofficial==0.1.0
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_TEXT_PROMPT = "top. outer. skirt. pants. dress. shoes. bag. accessory."
DEFAULT_CONFIDENCE = 0.30


@dataclass
class BBox:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    confidence: float


_gdino_model = None


def _load_model():
    global _gdino_model
    if _gdino_model is not None:
        return _gdino_model

    settings = get_settings()
    try:
        from groundingdino.util.inference import load_model  # type: ignore
        _gdino_model = load_model(
            model_config_path=settings.gdino_config,
            model_checkpoint_path=settings.gdino_checkpoint,
        )
        logger.info("[detect_gdino] Grounding DINO 모델 로드 완료")
    except ImportError:
        logger.error("[detect_gdino] groundingdino-unofficial 패키지가 없습니다. pip install groundingdino-unofficial==0.1.0")
        raise
    return _gdino_model


def detect_garments(
    image_path: str | Path,
    text_prompt: str = DEFAULT_TEXT_PROMPT,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> list[BBox]:
    """이미지에서 의류 아이템 bbox 감지.

    Args:
        image_path: 분석할 이미지 경로
        text_prompt: 감지할 카테고리 텍스트 (GroundingDINO 형식)
        confidence_threshold: 최소 신뢰도 임계값

    Returns:
        BBox 리스트 (confidence 내림차순)
    """
    from groundingdino.util.inference import predict, load_image  # type: ignore

    model = _load_model()
    image_source, image = load_image(str(image_path))

    boxes, logits, phrases = predict(
        model=model,
        image=image,
        caption=text_prompt,
        box_threshold=confidence_threshold,
        text_threshold=confidence_threshold,
    )

    h, w = image_source.shape[:2]
    results: list[BBox] = []

    for box, logit, phrase in zip(boxes, logits, phrases):
        cx, cy, bw, bh = box.tolist()
        x1 = (cx - bw / 2) * w
        y1 = (cy - bh / 2) * h
        x2 = (cx + bw / 2) * w
        y2 = (cy + bh / 2) * h
        results.append(BBox(x1=x1, y1=y1, x2=x2, y2=y2, label=phrase, confidence=float(logit)))

    results.sort(key=lambda b: b.confidence, reverse=True)
    logger.info("[detect_gdino] %d개 의류 감지 완료", len(results))
    return results
