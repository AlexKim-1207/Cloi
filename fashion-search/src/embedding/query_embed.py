"""Query 이미지 임베딩 (search 요청 경로 전용)."""
import io
import logging

import numpy as np
from PIL import Image

from .openclip_embed import embed_single

logger = logging.getLogger(__name__)


def embed_query_bytes(image_bytes: bytes) -> np.ndarray:
    """bytes → 임베딩 벡터.

    Args:
        image_bytes: 이미지 bytes

    Returns:
        shape (D,) float32 ndarray
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    vec = embed_single(image)
    logger.debug("[query_embed] 임베딩 완료, dim=%d", len(vec))
    return vec


def embed_query_crop(crop_image: Image.Image) -> np.ndarray:
    """GarmentCrop.crop_image → 임베딩 벡터."""
    return embed_single(crop_image.convert("RGB"))
