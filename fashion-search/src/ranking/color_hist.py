"""HSV 기반 색상 매칭 + dominant color 추출.

기존 RGB cosine의 약점 해결:
- HSV: 색조(H) 분리 → 회색과 핑크 명확히 구분
- dominant: K-means로 주요 색상 3개 추출 → 배경 노이즈 감소
"""
from typing import Optional

import numpy as np
from PIL import Image


def _pil_to_hsv_arr(image: Image.Image) -> np.ndarray:
    """PIL image → numpy HSV array normalized to [0, 1]."""
    hsv_img = image.convert('HSV')
    return np.array(hsv_img).astype(np.float32) / 255.0


def compute_color_histogram(
    image: Image.Image,
    h_bins: int = 12,
    s_bins: int = 4,
    v_bins: int = 4,
) -> np.ndarray:
    """HSV 3D 히스토그램. 색조(H) 12 bin, 채도(S)/명도(V) 4 bin.

    H가 12 bin으로 세분화되어 회색(S=0)과 핑크(H=300)가 명확히 분리됨.
    Returns: (h_bins * s_bins * v_bins,) = (192,) 정규화된 벡터
    """
    hsv = _pil_to_hsv_arr(image)
    hist, _ = np.histogramdd(
        hsv.reshape(-1, 3),
        bins=[h_bins, s_bins, v_bins],
        range=[(0.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
    )
    flat = hist.flatten()
    norm = np.linalg.norm(flat) + 1e-8
    return flat / norm


def extract_dominant_colors(image: Image.Image, k: int = 3) -> np.ndarray:
    """K-means로 dominant color k개 추출 (HSV 공간).

    Returns: (k, 3) HSV 벡터.
    """
    try:
        from sklearn.cluster import KMeans
    except ImportError:
        small = image.resize((32, 32))
        hsv = _pil_to_hsv_arr(small).reshape(-1, 3)
        mean = hsv.mean(axis=0)
        return np.tile(mean, (k, 1))

    small = image.resize((64, 64))
    hsv = _pil_to_hsv_arr(small).reshape(-1, 3)
    km = KMeans(n_clusters=k, random_state=42, n_init=3, max_iter=20)
    km.fit(hsv)
    return km.cluster_centers_


def color_similarity(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """HSV 히스토그램 코사인 유사도 (0~1)."""
    sim = float(np.dot(hist_a, hist_b))
    return max(0.0, min(1.0, sim))


def dominant_color_similarity(
    domains_a: np.ndarray,
    domains_b: np.ndarray,
) -> float:
    """Dominant color 매칭 유사도.

    각 a의 색을 가장 비슷한 b 색과 매칭, 평균 유사도 반환.
    HSV 거리: 색조(H)에 가중치 큼 (×3).
    """
    if domains_a is None or domains_b is None:
        return 0.5
    sims = []
    for ca in domains_a:
        dists = np.linalg.norm(
            (domains_b - ca) * np.array([3.0, 1.0, 1.0]),
            axis=1,
        )
        best_dist = float(dists.min())
        sims.append(max(0.0, 1.0 - best_dist))
    return float(np.mean(sims))


def color_score(
    query_hist: np.ndarray,
    product_hist: np.ndarray,
    query_dominant: Optional[np.ndarray] = None,
    product_dominant: Optional[np.ndarray] = None,
) -> float:
    """종합 색상 점수: 히스토그램 40% + dominant 60%.

    dominant 없으면 히스토그램만 사용.
    """
    hist_sim = color_similarity(query_hist, product_hist)
    if query_dominant is not None and product_dominant is not None:
        dom_sim = dominant_color_similarity(query_dominant, product_dominant)
        return hist_sim * 0.40 + dom_sim * 0.60
    return hist_sim
