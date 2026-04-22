"""카탈로그 이미지 전체 배치 임베딩 + FAISS 인덱스 빌드.

Usage:
    python -m scripts.build_catalog_index [--catalog-dir PATH] [--batch-size N]

체크포인트 기능:
    - 중단 후 재실행 시 이전 진행분부터 이어서 실행
    - artifacts/catalog_vectors_partial.npy + catalog_meta_partial.json 에 저장
    - 완료 시 artifacts/catalog.index + catalog_meta.json 으로 최종 저장
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings
from src.embedding.catalog_embed_job import build_embeddings
from src.search.faiss_store import FAISSStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("build_catalog_index")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="카탈로그 FAISS 인덱스 빌드")
    parser.add_argument(
        "--catalog-dir",
        type=str,
        default=None,
        help="카탈로그 이미지 디렉토리 (기본: settings.catalog_dir)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="임베딩 배치 크기 (기본: 32)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()

    artifacts_dir = settings.artifacts_dir
    index_path = os.path.join(artifacts_dir, "catalog.index")

    logger.info("=== 카탈로그 인덱스 빌드 시작 ===")
    logger.info("catalog_dir : %s", args.catalog_dir or settings.catalog_dir)
    logger.info("artifacts   : %s", artifacts_dir)
    logger.info("batch_size  : %d", args.batch_size)

    # 1. 배치 임베딩 (체크포인트 기반)
    vectors, meta = build_embeddings(
        catalog_dir=args.catalog_dir,
        batch_size=args.batch_size,
    )

    if len(meta) == 0:
        logger.error("임베딩된 이미지가 없습니다. catalog_dir 경로를 확인하세요.")
        sys.exit(1)

    logger.info("임베딩 완료: %d개 벡터, dim=%d", len(meta), vectors.shape[1])

    # 2. FAISS 인덱스 빌드
    logger.info("FAISS 인덱스 빌드 중...")
    store = FAISSStore(dim=vectors.shape[1])
    store.build(vectors, meta)
    logger.info("인덱스 크기: %d", store.size())

    # 3. 저장
    Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
    store.save(index_path)
    logger.info("인덱스 저장 완료: %s", index_path)

    # 4. 체크포인트 파일 정리
    partial_vec = os.path.join(artifacts_dir, "catalog_vectors_partial.npy")
    partial_meta = os.path.join(artifacts_dir, "catalog_meta_partial.json")
    for f in [partial_vec, partial_meta]:
        if os.path.exists(f):
            os.remove(f)
            logger.info("체크포인트 삭제: %s", f)

    logger.info("=== 빌드 완료 ===")


if __name__ == "__main__":
    main()
