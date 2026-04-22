"""카탈로그 이미지 배치 임베딩 + 체크포인트 저장.

scripts/build_catalog_index.py에서 호출.
"""
import json
import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm

from .openclip_embed import embed_images, load_clip_model
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

CHECKPOINT_FILE = "catalog_vectors_partial.npy"
CHECKPOINT_META_FILE = "catalog_meta_partial.json"


def build_embeddings(
    catalog_dir: str | None = None,
    batch_size: int = 32,
) -> tuple[np.ndarray, list[dict]]:
    """카탈로그 이미지 전체 임베딩 (배치 + 체크포인트).

    Args:
        catalog_dir: 이미지 디렉토리 경로
        batch_size: 배치 크기

    Returns:
        (vectors: ndarray(N, D), meta: list[dict])
    """
    settings = get_settings()
    catalog_dir = catalog_dir or settings.catalog_dir
    artifacts_dir = settings.artifacts_dir

    load_clip_model()

    # 이미지 파일 목록
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    all_paths = sorted(
        p for p in Path(catalog_dir).rglob("*") if p.suffix.lower() in exts
    )
    logger.info("[catalog_embed] 총 %d개 이미지 발견", len(all_paths))

    # 체크포인트 로드 (중단 후 이어서 실행)
    checkpoint_path = os.path.join(artifacts_dir, CHECKPOINT_FILE)
    meta_checkpoint_path = os.path.join(artifacts_dir, CHECKPOINT_META_FILE)

    done_vectors: list[np.ndarray] = []
    done_meta: list[dict] = []
    start_idx = 0

    if os.path.exists(checkpoint_path) and os.path.exists(meta_checkpoint_path):
        done_vectors_arr = np.load(checkpoint_path)
        with open(meta_checkpoint_path, encoding="utf-8") as f:
            done_meta = json.load(f)
        start_idx = len(done_meta)
        done_vectors = [done_vectors_arr]
        logger.info("[catalog_embed] 체크포인트 로드: %d개 완료, %d개 남음", start_idx, len(all_paths) - start_idx)

    remaining = all_paths[start_idx:]
    if not remaining:
        logger.info("[catalog_embed] 모든 이미지 처리 완료 (체크포인트)")
        arr = np.vstack(done_vectors) if done_vectors else np.empty((0, 768), dtype=np.float32)
        return arr, done_meta

    new_vectors: list[np.ndarray] = []
    new_meta: list[dict] = []

    for i in tqdm(range(0, len(remaining), batch_size), desc="임베딩 중"):
        batch_paths = remaining[i : i + batch_size]
        batch_images: list[Image.Image] = []
        valid_paths: list[Path] = []

        for p in batch_paths:
            try:
                img = Image.open(p).convert("RGB")
                batch_images.append(img)
                valid_paths.append(p)
            except Exception:
                logger.warning("[catalog_embed] 이미지 로드 실패: %s", p)

        if not batch_images:
            continue

        vecs = embed_images(batch_images, batch_size=batch_size)
        new_vectors.append(vecs)
        new_meta.extend(
            {"product_id": p.stem, "path": str(p)} for p in valid_paths
        )

        # 체크포인트 저장
        all_vecs = np.vstack(done_vectors + new_vectors)
        all_meta = done_meta + new_meta
        Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
        np.save(checkpoint_path, all_vecs)
        with open(meta_checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(all_meta, f, ensure_ascii=False)

    final_vectors = np.vstack(done_vectors + new_vectors) if (done_vectors or new_vectors) else np.empty((0, 768), dtype=np.float32)
    final_meta = done_meta + new_meta
    logger.info("[catalog_embed] 임베딩 완료: %d개", len(final_meta))
    return final_vectors, final_meta
