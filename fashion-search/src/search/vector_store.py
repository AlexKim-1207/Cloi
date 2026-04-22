from abc import ABC, abstractmethod
import numpy as np


class VectorStore(ABC):
    """VectorStore 추상 인터페이스 — FAISSStore, MilvusStore 등이 구현."""

    @abstractmethod
    def build(self, vectors: np.ndarray, meta: list[dict]) -> None:
        """벡터 + 메타데이터로 인덱스 초기 구축."""
        ...

    @abstractmethod
    def search(self, query: np.ndarray, k: int = 50) -> tuple[np.ndarray, list[int]]:
        """query 벡터로 유사 상품 검색.

        Returns:
            (distances, indices): distances shape (k,), indices shape (k,)
        """
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """인덱스를 디스크에 저장."""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """디스크에서 인덱스 로드."""
        ...

    @abstractmethod
    def add(self, vectors: np.ndarray, meta: list[dict]) -> None:
        """카탈로그 업데이트용 증분 추가."""
        ...

    @abstractmethod
    def size(self) -> int:
        """현재 인덱스에 등록된 벡터 수."""
        ...
