"""FashionCLIP zero-shot 시각 속성 분류기."""
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

from src.embedding.fashion_clip_embedder import FashionCLIPEmbedder

NECKLINE_OPTIONS = [
    'v-neck top', 'round neck top', 'turtleneck sweater',
    'off-shoulder top', 'square neck top', 'collared shirt',
    'henley neck top', 'crew neck',
]
FIT_OPTIONS = [
    'oversized loose fit clothing', 'slim fit clothing',
    'regular fit clothing', 'cropped fit top', 'boxy fit',
]
SLEEVE_OPTIONS = [
    'short sleeve', 'long sleeve', 'sleeveless',
    'three quarter sleeve', 'puff sleeve',
]
MATERIAL_OPTIONS = [
    'cable knit sweater', 'denim', 'linen fabric', 'chiffon',
    'leather', 'cotton', 'satin', 'wool', 'tweed', 'lace',
]
PATTERN_OPTIONS = [
    'solid color', 'striped pattern', 'floral pattern',
    'check pattern', 'graphic print', 'animal print',
]
BAG_OPTIONS = [
    'chain shoulder bag', 'tote bag', 'crossbody bag',
    'clutch bag', 'backpack', 'mini bag', 'bucket bag',
]
SHOE_OPTIONS = [
    'sneakers', 'heels', 'loafers', 'boots',
    'sandals', 'flats', 'mules',
]
MOOD_OPTIONS = [
    'luxury fashion editorial elegant',
    'casual street style daily',
    'minimal office professional clean',
    'sporty athletic wear',
    'feminine romantic look',
    'vintage retro style',
    'y2k playful trendy',
    'classic timeless preppy',
]


class AttributeClassifier:
    def __init__(self, embedder: FashionCLIPEmbedder):
        self.embedder = embedder
        self._text_cache: Dict[str, np.ndarray] = {}

    def _encode_texts(self, texts: List[str]) -> np.ndarray:
        key = '||'.join(texts)
        if key not in self._text_cache:
            self._text_cache[key] = self.embedder.encode_text(texts)
        return self._text_cache[key]

    def _top_k(self, image_emb: np.ndarray, options: List[str], k: int = 1) -> List[Tuple[str, float]]:
        text_embs = self._encode_texts(options)
        scores = (image_emb @ text_embs.T).flatten()
        top_idx = scores.argsort()[::-1][:k]
        return [(options[i], float(scores[i])) for i in top_idx]

    def classify_all(self, image: Image.Image) -> Dict:
        image_emb = self.embedder.embed_single(image)
        if image_emb.ndim == 1:
            image_emb = image_emb[np.newaxis, :]

        mood_top = self._top_k(image_emb, MOOD_OPTIONS, k=1)[0]

        return {
            'neckline': self._top_k(image_emb, NECKLINE_OPTIONS, k=1)[0][0],
            'fit': self._top_k(image_emb, FIT_OPTIONS, k=1)[0][0],
            'sleeve': self._top_k(image_emb, SLEEVE_OPTIONS, k=1)[0][0],
            'material': self._top_k(image_emb, MATERIAL_OPTIONS, k=2),
            'pattern': self._top_k(image_emb, PATTERN_OPTIONS, k=1)[0][0],
            'mood': mood_top[0],
            'mood_confidence': mood_top[1],
        }
