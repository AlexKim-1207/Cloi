"""전처리 파이프라인 통합.

순서:
1. Grounding DINO → 의류 box
2. PaddleOCR → 텍스트 box → 마스킹
3. Haar Cascade → 얼굴 box → 마스킹
4. 의류 crop 추출 (8% expand)
"""
from typing import Dict, Any, List
from PIL import Image
from src.preprocess.garment_detect import detect_garments
from src.preprocess.text_mask import detect_text_boxes, blur_boxes
from src.preprocess.face_mask import detect_faces, blur_faces


def _expand_box(box: List[int], w: int, h: int, ratio: float = 0.08) -> List[int]:
    x1, y1, x2, y2 = box
    dx, dy = int((x2 - x1) * ratio), int((y2 - y1) * ratio)
    return [
        max(0, x1 - dx), max(0, y1 - dy),
        min(w, x2 + dx), min(h, y2 + dy),
    ]


def preprocess_image(img: Image.Image) -> Dict[str, Any]:
    """전처리 통합 실행.

    Returns:
        {
            'garments': [{label, score, box, crop_box, crop}, ...],
            'face_boxes': [[x1,y1,x2,y2], ...],
            'text_boxes': [[x1,y1,x2,y2], ...],
            'masked_image': PIL.Image (얼굴/텍스트 마스킹된 원본)
        }
    """
    img = img.convert("RGB")
    w, h = img.size

    garments = detect_garments(img)
    faces = detect_faces(img)
    texts = detect_text_boxes(img)

    masked = blur_faces(img, faces)
    masked = blur_boxes(masked, texts)

    crops = []
    for g in garments:
        crop_box = _expand_box(g["box"], w, h, ratio=0.08)
        x1, y1, x2, y2 = crop_box
        crop = masked.crop((x1, y1, x2, y2))
        crops.append({**g, "crop_box": crop_box, "crop": crop})

    return {
        "garments": crops,
        "face_boxes": faces,
        "text_boxes": texts,
        "masked_image": masked,
    }
