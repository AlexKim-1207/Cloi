import math
import json
import os
import numpy as np
import faiss

from .vector_store import VectorStore


class FAISSStore(VectorStore):
    """FAISS IndexIVFFlat 기반 VectorStore 구현.

    IndexFlatIP(exact) 대신 IndexIVFFlat(approximate)을 사용해
    상품 수 증가에도 검색 속도를 유지.
    """

    def __init__(self, dim: int = 768, nprobe: int = 10) -> None:
        self.dim = dim
        self.nprobe = nprobe
        self.index: faiss.Index | None = None
        self.meta: list[dict] = []

    # ── 내부 유틸 ──────────────────────────────────────────────────────────────

    def _make_index(self, n: int) -> faiss.IndexIVFFlat:
        nlist = max(64, int(math.sqrt(n)))
        quantizer = faiss.IndexFlatIP(self.dim)
        index = faiss.IndexIVFFlat(quantizer, self.dim, nlist, faiss.METRIC_INNER_PRODUCT)
        index.nprobe = self.nprobe
        return index

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        return (vectors / norms).astype(np.float32)

    # ── VectorStore 구현 ───────────────────────────────────────────────────────

    def build(self, vectors: np.ndarray, meta: list[dict]) -> None:
        vectors = self._normalize(vectors)
        self.index = self._make_index(len(vectors))
        self.index.train(vectors)
        self.index.add(vectors)
        self.meta = list(meta)

    def search(self, query: np.ndarray, k: int = 50) -> tuple[np.ndarray, list[int]]:
        if self.index is None:
            raise RuntimeError("FAISSStore: index가 비어 있습니다. build() 또는 load() 먼저 호출하세요.")
        query = self._normalize(query.reshape(1, -1))
        distances, indices = self.index.search(query, k)
        return distances[0], indices[0].tolist()

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        faiss.write_index(self.index, path)
        meta_path = path.replace(".index", "_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False)

    def load(self, path: str) -> None:
        self.index = faiss.read_index(path)
        self.index.nprobe = self.nprobe
        meta_path = path.replace(".index", "_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                self.meta = json.load(f)

    def add(self, vectors: np.ndarray, meta: list[dict]) -> None:
        if self.index is None:
            self.build(vectors, meta)
            return
        vectors = self._normalize(vectors)
        self.index.add(vectors)
        self.meta.extend(meta)

    def size(self) -> int:
        return self.index.ntotal if self.index else 0

    def get_meta(self, idx: int) -> dict:
        if 0 <= idx < len(self.meta):
            return self.meta[idx]
        return {}
