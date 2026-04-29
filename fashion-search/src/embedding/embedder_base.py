from abc import ABC, abstractmethod
import numpy as np
from PIL import Image


class ImageEmbedder(ABC):
    name: str
    dim: int

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def embed(self, images: list[Image.Image]) -> np.ndarray:
        """Return L2-normalized (N, dim) float32 array."""
        ...

    def embed_single(self, image: Image.Image) -> np.ndarray:
        return self.embed([image])[0]
