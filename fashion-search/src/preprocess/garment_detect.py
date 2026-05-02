"""Grounding DINO 기반 의류 box 탐지.

보고서 추천:
- IDEA-Research/grounding-dino-base
- text prompt: 의류/신발/액세서리 카테고리
- box_threshold=0.28, text_threshold=0.20
"""
from __future__ import annotations
from typing import List, Dict, Any
import torch
from PIL import Image

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_GARMENT_PROMPT = (
    "cardigan. sweater. knit top. blouse. shirt. jacket. coat. vest. "
    "dress. skirt. pants. jeans. shorts. shoes. bag. hat. necklace. "
    "earring. ring. belt. watch. sunglasses."
)

_processor = None
_model = None


def _load() -> None:
    global _processor, _model
    if _model is not None:
        return
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    _processor = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
    _model = AutoModelForZeroShotObjectDetection.from_pretrained(
        "IDEA-Research/grounding-dino-base"
    ).to(DEVICE)
    _model.eval()


def detect_garments(
    img: Image.Image,
    box_threshold: float = 0.28,
    text_threshold: float = 0.20,
) -> List[Dict[str, Any]]:
    """이미지에서 의류 box 탐지.

    Returns:
        [{label, score, box: [x1,y1,x2,y2]}, ...]
    """
    _load()
    proc = _processor
    mdl = _model
    assert proc is not None and mdl is not None
    inputs = proc(images=img, text=_GARMENT_PROMPT, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = mdl(**inputs)
    results = proc.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[img.size[::-1]],
    )[0]

    out = []
    for box, label, score in zip(
        results["boxes"].cpu().numpy().tolist(),
        results["labels"],
        results["scores"].cpu().numpy().tolist(),
    ):
        x1, y1, x2, y2 = map(int, box)
        out.append({
            "label": str(label),
            "score": float(score),
            "box": [x1, y1, x2, y2],
        })
    return out
