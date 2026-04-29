import numpy as np
import torch
from PIL import Image

from src.embedding.embedder_base import ImageEmbedder

_MODEL_ID = "Marqo/marqo-fashionSigLIP"


class MarqoSigLIPEmbedder(ImageEmbedder):
    name = "marqo_fashion_siglip"
    dim = 768

    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self._model = None
        self._processor = None

    def load(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoModel, AutoProcessor  # type: ignore
        self._model = AutoModel.from_pretrained(_MODEL_ID, trust_remote_code=True)
        self._processor = AutoProcessor.from_pretrained(_MODEL_ID, trust_remote_code=True)
        self._model.eval()

    def embed(self, images: list[Image.Image]) -> np.ndarray:
        if self._model is None:
            self.load()
        all_features: list[np.ndarray] = []
        for i in range(0, len(images), self.batch_size):
            batch = images[i : i + self.batch_size]
            inputs = self._processor(images=batch, return_tensors="pt")
            with torch.no_grad():
                feats = self._model.get_image_features(**inputs).cpu().numpy().astype(np.float32)
            norms = np.linalg.norm(feats, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1e-9, norms)
            all_features.append(feats / norms)
        return np.vstack(all_features) if all_features else np.empty((0, self.dim), dtype=np.float32)
