"""카탈로그 FAISS 인덱스 빌드 (임베더 선택 가능).

Usage:
    python -m scripts.build_catalog_index --embedder marqo_fashion_siglip
    python -m scripts.build_catalog_index --embedder openclip_vitl14
    python -m scripts.build_catalog_index --embedder fashion_clip

출력:
    artifacts/{embedder_name}.faiss
    artifacts/{embedder_name}_meta.db  (SQLite)

체크포인트:
    artifacts/{embedder_name}_partial.npy
    artifacts/{embedder_name}_partial_meta.json
    100개마다 저장. 중단 후 재실행 시 이어서 진행.
"""
import argparse
import json
import logging
import math
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import faiss
import numpy as np
from PIL import Image
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings
from src.embedding import get_embedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] — %(message)s",
)
logger = logging.getLogger("build_catalog_index")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--embedder",
        choices=["openclip_vitl14", "fashion_clip", "marqo_fashion_siglip"],
        default="marqo_fashion_siglip",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--catalog-dir", type=str, default=None)
    return parser.parse_args()


def init_meta_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS catalog (
            faiss_id  INTEGER PRIMARY KEY,
            product_id TEXT,
            category   TEXT,
            subcategory TEXT,
            color      TEXT,
            gender     TEXT,
            name       TEXT,
            path       TEXT
        )
    """)
    conn.commit()
    return conn


def save_faiss(index: faiss.Index, out_path: Path) -> None:
    # FAISS C++ bug on Windows with non-ASCII paths — copy via ASCII temp dir
    with tempfile.TemporaryDirectory(prefix="faiss_") as tmp:
        tmp_path = Path(tmp) / "out.faiss"
        faiss.write_index(index, str(tmp_path))
        shutil.copy2(str(tmp_path), str(out_path))


def main() -> None:
    args = parse_args()
    settings = get_settings()

    catalog_dir = Path(args.catalog_dir or settings.catalog_dir)
    artifacts_dir = Path(settings.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = catalog_dir / "catalog.jsonl"
    if not jsonl_path.exists():
        logger.error("catalog.jsonl 없음: %s — seed_catalog.py 먼저 실행하세요.", jsonl_path)
        sys.exit(1)

    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    logger.info("카탈로그 항목: %d개", len(records))

    # Load embedder
    logger.info("임베더 로드: %s", args.embedder)
    embedder = get_embedder(args.embedder)
    embedder.load()
    logger.info("임베더 준비 완료 (dim=%d)", embedder.dim)

    # Checkpoint
    ckpt_vecs_path = artifacts_dir / f"{args.embedder}_partial.npy"
    ckpt_meta_path = artifacts_dir / f"{args.embedder}_partial_meta.json"

    done_vecs: list[np.ndarray] = []
    done_meta: list[dict] = []
    start_idx = 0

    if ckpt_vecs_path.exists() and ckpt_meta_path.exists():
        arr = np.load(str(ckpt_vecs_path))
        with open(ckpt_meta_path, encoding="utf-8") as f:
            done_meta = json.load(f)
        start_idx = len(done_meta)
        done_vecs = [arr]
        logger.info("체크포인트 로드: %d개 완료, %d개 남음", start_idx, len(records) - start_idx)

    remaining = records[start_idx:]
    new_vecs: list[np.ndarray] = []
    new_meta: list[dict] = []
    processed_since_ckpt = 0

    for i in tqdm(range(0, len(remaining), args.batch_size), desc=f"[{args.embedder}]"):
        batch_records = remaining[i : i + args.batch_size]
        batch_images: list[Image.Image] = []
        batch_valid: list[dict] = []

        for rec in batch_records:
            img_path = catalog_dir / f"{rec['product_id']}.jpg"
            if not img_path.exists():
                logger.warning("이미지 없음: %s", img_path)
                continue
            try:
                img = Image.open(str(img_path)).convert("RGB")
                batch_images.append(img)
                batch_valid.append({**rec, "path": str(img_path)})
            except Exception as e:
                logger.warning("로드 실패 %s: %s", img_path, e)

        if not batch_images:
            continue

        vecs = embedder.embed(batch_images)
        new_vecs.append(vecs)
        new_meta.extend(batch_valid)
        processed_since_ckpt += len(batch_valid)

        # Checkpoint every 100 items
        if processed_since_ckpt >= 100:
            all_v = np.vstack(done_vecs + new_vecs)
            all_m = done_meta + new_meta
            np.save(str(ckpt_vecs_path), all_v)
            with open(ckpt_meta_path, "w", encoding="utf-8") as f:
                json.dump(all_m, f, ensure_ascii=False)
            logger.info("체크포인트 저장: %d개", len(all_m))
            processed_since_ckpt = 0

    # Final assembly
    all_vecs_parts = done_vecs + new_vecs
    if not all_vecs_parts:
        logger.error("임베딩된 벡터 없음.")
        sys.exit(1)

    all_vecs = np.vstack(all_vecs_parts).astype(np.float32)
    all_meta = done_meta + new_meta
    n = len(all_meta)
    dim = all_vecs.shape[1]
    logger.info("전체 임베딩 완료: %d개, dim=%d", n, dim)

    # L2-normalize (embedders return normalized, but ensure)
    norms = np.linalg.norm(all_vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    all_vecs = (all_vecs / norms).astype(np.float32)

    # Build FAISS IndexIVFFlat
    nlist = max(64, int(math.sqrt(n)))
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
    index.nprobe = 10
    index.train(all_vecs)
    index.add(all_vecs)
    logger.info("FAISS ntotal=%d", index.ntotal)

    # Save .faiss
    faiss_path = artifacts_dir / f"{args.embedder}.faiss"
    save_faiss(index, faiss_path)
    logger.info("FAISS 저장: %s", faiss_path)

    # Save _meta.db (SQLite)
    db_path = str(artifacts_dir / f"{args.embedder}_meta.db")
    conn = init_meta_db(db_path)
    conn.execute("DELETE FROM catalog")
    conn.executemany(
        "INSERT INTO catalog "
        "(faiss_id, product_id, category, subcategory, color, gender, name, path) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                i,
                m["product_id"],
                m.get("category", ""),
                m.get("subcategory", ""),
                m.get("color", ""),
                m.get("gender", ""),
                m.get("name", ""),
                m.get("path", ""),
            )
            for i, m in enumerate(all_meta)
        ],
    )
    conn.commit()
    conn.close()
    logger.info("메타 DB 저장: %s", db_path)

    # Cleanup checkpoints
    for ckpt in [ckpt_vecs_path, ckpt_meta_path]:
        if ckpt.exists():
            ckpt.unlink()
            logger.info("체크포인트 삭제: %s", ckpt)

    logger.info("=== 빌드 완료: %s (ntotal=%d) ===", args.embedder, index.ntotal)


if __name__ == "__main__":
    main()
