"""유저 업로드 이미지 카탈로그 자동 추가 (BackgroundTask용)."""
import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# 동시 write 경쟁 조건 방지
_CATALOG_LOCK = threading.Lock()


def _save_index_safe(store, index_path: str) -> None:
    """한글 경로 FAISS write 버그 우회 — ASCII 임시 경로에 저장 후 복사."""
    import faiss

    with tempfile.TemporaryDirectory(prefix="faiss_w_") as tmp:
        tmp_idx = os.path.join(tmp, "tmp.index")
        faiss.write_index(store.index, tmp_idx)
        shutil.copy2(tmp_idx, index_path)

    meta_path = index_path.replace(".index", "_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(store.meta, f, ensure_ascii=False, indent=2)


def contribute_image_to_catalog(
    image_bytes: bytes,
    img_hash: str,
    store,
    index_path: str,
    catalog_images_dir: str,
) -> None:
    """유저 동의 이미지를 카탈로그에 추가한다.

    - 중복(같은 SHA256) 자동 스킵
    - FAISS 인덱스 + catalog_meta.json 실시간 갱신
    - 서버 재시작 없이 즉시 검색에 반영됨
    """
    from src.embedding.query_embed import embed_query_bytes

    with _CATALOG_LOCK:
        # 1. 중복 확인
        existing_ids = {m.get("product_id") for m in store.meta}
        if img_hash in existing_ids:
            logger.info("[contributor] 중복 스킵: %s...", img_hash[:16])
            return

        # 2. 이미지 파일 저장
        images_dir = Path(catalog_images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        img_path = images_dir / f"{img_hash}.jpg"
        img_path.write_bytes(image_bytes)
        logger.info("[contributor] 이미지 저장: %s", img_path.name)

        # 3. 임베딩 생성
        try:
            vec: np.ndarray = embed_query_bytes(image_bytes)
        except Exception as exc:
            logger.warning("[contributor] 임베딩 실패 — 이미지 삭제 후 종료: %s", exc)
            img_path.unlink(missing_ok=True)
            return

        # 4. FAISS 인덱스에 추가 (in-memory)
        meta_entry = {
            "product_id": img_hash,
            "image_url": str(img_path),
            "name": "유저 업로드",
            "brand": "",
            "price": 0,
            "category": "user_upload",
            "shop_url": "",
            "source": "user_contribution",
        }
        store.add(vec.reshape(1, -1), [meta_entry])
        logger.info("[contributor] FAISS 추가 완료 (인덱스 크기=%d)", store.size())

        # 5. 인덱스 + 메타 디스크 영속화
        try:
            _save_index_safe(store, index_path)
            logger.info("[contributor] 인덱스 저장 완료: %s", index_path)
        except Exception as exc:
            logger.warning("[contributor] 인덱스 저장 실패 (in-memory 반영은 유지): %s", exc)
