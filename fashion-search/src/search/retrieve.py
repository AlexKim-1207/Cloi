"""VectorStore를 이용한 유사 벡터 검색 (async).

SearchCandidate: 상위 결과 + score를 담는 데이터 클래스.
"""
import asyncio
import logging
from dataclasses import dataclass

import numpy as np

from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class SearchCandidate:
    """단일 검색 후보.

    Attributes:
        product_id: 카탈로그 상품 ID (파일명 stem)
        path: 카탈로그 이미지 경로
        score: 코사인 유사도 (0~1, 높을수록 유사)
        meta: 추가 메타 정보 dict
    """
    product_id: str
    path: str
    score: float
    meta: dict


async def search_similar(
    query_vector: np.ndarray,
    store: VectorStore,
    k: int = 50,
) -> list[SearchCandidate]:
    """query_vector와 유사한 상위 k개 카탈로그 반환 (비동기).

    CPU 집약적인 FAISS 검색을 executor로 오프로드.

    Args:
        query_vector: shape (D,) float32 쿼리 임베딩
        store: 초기화된 VectorStore 인스턴스
        k: 반환할 최대 후보 수

    Returns:
        SearchCandidate 리스트 (score 내림차순)
    """
    loop = asyncio.get_event_loop()
    distances, indices = await loop.run_in_executor(
        None, store.search, query_vector, k
    )

    candidates: list[SearchCandidate] = []
    for dist, idx in zip(distances, indices):
        if idx < 0:  # FAISS 패딩 인덱스 (-1) 스킵
            continue
        meta = store.get_meta(idx)
        if not meta:
            continue
        candidates.append(
            SearchCandidate(
                product_id=meta.get("product_id", str(idx)),
                path=meta.get("path", ""),
                score=float(dist),
                meta=meta,
            )
        )

    logger.debug("[retrieve] FAISS 검색 완료: %d개 후보 (k=%d)", len(candidates), k)
    return candidates
