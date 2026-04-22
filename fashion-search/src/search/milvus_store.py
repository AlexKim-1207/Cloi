"""MilvusStore — TODO stub (VectorStore 인터페이스 준수).

FAISSStore 대신 Milvus/Zilliz Cloud로 마이그레이션할 때 구현.
현재는 NotImplementedError를 raise하며 인터페이스만 정의.
"""
import numpy as np

from .vector_store import VectorStore


class MilvusStore(VectorStore):
    """TODO: Milvus/Zilliz Cloud 기반 VectorStore 구현체.

    참고:
        pip install pymilvus>=2.4.0
        환경 변수: MILVUS_URI, MILVUS_TOKEN
    """

    def __init__(self, collection_name: str = "fashion_catalog") -> None:
        self.collection_name = collection_name

    def build(self, vectors: np.ndarray, meta: list[dict]) -> None:
        raise NotImplementedError("MilvusStore.build() — 미구현 (TODO)")

    def search(self, query: np.ndarray, k: int = 50) -> tuple[np.ndarray, list[int]]:
        raise NotImplementedError("MilvusStore.search() — 미구현 (TODO)")

    def save(self, path: str) -> None:
        raise NotImplementedError("MilvusStore.save() — Milvus는 클라우드 영속성 사용")

    def load(self, path: str) -> None:
        raise NotImplementedError("MilvusStore.load() — Milvus는 클라우드 영속성 사용")

    def add(self, vectors: np.ndarray, meta: list[dict]) -> None:
        raise NotImplementedError("MilvusStore.add() — 미구현 (TODO)")

    def size(self) -> int:
        raise NotImplementedError("MilvusStore.size() — 미구현 (TODO)")

    def get_meta(self, idx: int) -> dict:
        raise NotImplementedError("MilvusStore.get_meta() — 미구현 (TODO)")
