"""RGB 색상 히스토그램 보조 유사도 신호.

FashionCLIP의 미세 색상 농도(찐핑크 vs 연핑크) 약점 보완.
"""
import numpy as np
from PIL import Image


def compute_color_histogram(image: Image.Image, bins: int = 8) -> np.ndarray:
    """RGB 3채널 각각 bins개로 히스토그램. 정규화된 1D 벡터 반환.

    Returns:
        (3 * bins,) 형태 정규화된 히스토그램.
    """
    arr = np.array(image.convert('RGB'))
    hist_r, _ = np.histogram(arr[:, :, 0], bins=bins, range=(0, 256), density=True)
    hist_g, _ = np.histogram(arr[:, :, 1], bins=bins, range=(0, 256), density=True)
    hist_b, _ = np.histogram(arr[:, :, 2], bins=bins, range=(0, 256), density=True)
    hist = np.concatenate([hist_r, hist_g, hist_b])
    norm = np.linalg.norm(hist) + 1e-8
    return hist / norm


def color_similarity(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """두 히스토그램 코사인 유사도 (0~1)."""
    sim = float(np.dot(hist_a, hist_b))
    return max(0.0, min(1.0, sim))
