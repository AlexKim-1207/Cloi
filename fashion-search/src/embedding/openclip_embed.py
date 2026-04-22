"""OpenCLIP ViT-L/14 임베딩 모듈.

pip install open_clip_torch==2.26.1
"""
import logging
from typing import TYPE_CHECKING

import numpy as np
import torch

from src.config.settings import get_settings

if TYPE_CHECKING:
    from PIL import Image as PILImage

logger = logging.getLogger(__name__)

_model = None
_preprocess = None
_tokenizer = None


def load_clip_model():
    """OpenCLIP 모델 preload (lifespan에서 호출)."""
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return

    settings = get_settings()
    try:
        import open_clip  # type: ignore
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            settings.clip_model,
            pretrained=settings.clip_pretrained,
        )
        _tokenizer = open_clip.get_tokenizer(settings.clip_model)
        _model.eval()
        logger.info("[openclip] 모델 로드 완료: %s (%s)", settings.clip_model, settings.clip_pretrained)
    except ImportError:
        logger.error("[openclip] open_clip_torch 패키지가 없습니다. pip install open_clip_torch==2.26.1")
        raise


def embed_images(images: list["PILImage.Image"], batch_size: int | None = None) -> np.ndarray:
    """PIL Image 리스트 → L2 정규화된 임베딩 행렬.

    Args:
        images: PIL Image 리스트
        batch_size: 배치 크기 (기본값: settings.clip_batch_size)

    Returns:
        shape (N, D) float32 ndarray, L2 정규화됨
    """
    if _model is None:
        load_clip_model()

    settings = get_settings()
    batch_size = batch_size or settings.clip_batch_size
    all_features: list[np.ndarray] = []

    for i in range(0, len(images), batch_size):
        batch = images[i : i + batch_size]
        tensors = torch.stack([_preprocess(img) for img in batch])
        with torch.no_grad():
            features = _model.encode_image(tensors)
        features = features.cpu().numpy().astype(np.float32)
        # L2 정규화
        norms = np.linalg.norm(features, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        features = features / norms
        all_features.append(features)

    return np.vstack(all_features) if all_features else np.empty((0, 768), dtype=np.float32)


def embed_single(image: "PILImage.Image") -> np.ndarray:
    """단일 이미지 임베딩 (query 전용)."""
    return embed_images([image])[0]
