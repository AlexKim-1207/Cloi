"""Lab + HSV-circular 색상 매칭 (SESSION 11 Track C).

기존 결함 해결:
- Hue 0.0과 1.0 같은 색 → min(d, 1-d) 처리
- Lab 색공간 = 인간 시각 거리에 가까움
- center_crop fallback (segmentation 불가 시 흰 여백 감소)
"""
from typing import Optional

import numpy as np
from PIL import Image


# ─── Lab 변환 ─────────────────────────────────────────────────────────────────

def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """RGB [0,255] → CIE Lab. sRGB → XYZ → Lab."""
    arr = rgb.astype(np.float32) / 255.0
    mask = arr > 0.04045
    arr = np.where(mask, ((arr + 0.055) / 1.055) ** 2.4, arr / 12.92)
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = arr @ M.T
    ref = np.array([0.95047, 1.0, 1.08883])
    xyz_ref = xyz / ref
    eps = 0.008856
    f = np.where(xyz_ref > eps, xyz_ref ** (1 / 3), (7.787 * xyz_ref) + 16 / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def compute_lab_histogram(image: Image.Image, l_bins: int = 8, ab_bins: int = 8) -> np.ndarray:
    """Lab 3D 히스토그램. L 8 bins (0~100), a/b 8 bins each (-128~127)."""
    rgb = np.array(image.convert('RGB'))
    lab = _rgb_to_lab(rgb).reshape(-1, 3)
    hist, _ = np.histogramdd(
        lab,
        bins=[l_bins, ab_bins, ab_bins],
        range=[(0, 100), (-128, 127), (-128, 127)],
    )
    flat = hist.flatten()
    norm = np.linalg.norm(flat) + 1e-8
    return flat / norm


# ─── HSV 순환 거리 ─────────────────────────────────────────────────────────────

def hue_circular_distance(h1: float, h2: float) -> float:
    """HSV Hue [0,1] 순환 거리. 빨강 0과 1은 같은 색."""
    d = abs(h1 - h2)
    return min(d, 1.0 - d)


# ─── center crop fallback ─────────────────────────────────────────────────────

def center_crop(image: Image.Image, ratio: float = 0.6) -> Image.Image:
    """중앙 ratio 영역만 crop — 흰 여백 비율 감소."""
    w, h = image.size
    cw, ch = int(w * ratio), int(h * ratio)
    left = (w - cw) // 2
    top = (h - ch) // 2
    return image.crop((left, top, left + cw, top + ch))


# ─── 점수 함수 ────────────────────────────────────────────────────────────────

def color_score_v2(query_hist: np.ndarray, product_hist: np.ndarray) -> float:
    """Lab 히스토그램 코사인 유사도. Hue 순환성 자동 해결 (Lab 순환 없음)."""
    sim = float(np.dot(query_hist, product_hist))
    return max(0.0, min(1.0, sim))


# ─── 레거시 HSV (하위 호환) ───────────────────────────────────────────────────

def _pil_to_hsv_arr(image: Image.Image) -> np.ndarray:
    hsv_img = image.convert('HSV')
    return np.array(hsv_img).astype(np.float32) / 255.0


def compute_color_histogram(
    image: Image.Image,
    h_bins: int = 12,
    s_bins: int = 4,
    v_bins: int = 4,
) -> np.ndarray:
    """레거시 HSV 히스토그램 — 신규 코드는 compute_lab_histogram 사용."""
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
    sim = float(np.dot(hist_a, hist_b))
    return max(0.0, min(1.0, sim))


def dominant_color_similarity(
    domains_a: np.ndarray,
    domains_b: np.ndarray,
) -> float:
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
    return color_similarity(query_hist, product_hist)
