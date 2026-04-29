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
        from transformers import SiglipModel, AutoProcessor  # type: ignore
        # SiglipModel avoids trust_remote_code meta-tensor bug in newer PyTorch
        self._model = SiglipModel.from_pretrained(_MODEL_ID)
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
                vision_out = self._model.vision_model(pixel_values=inputs["pixel_values"])
                feats = vision_out.pooler_output.cpu().numpy().astype(np.float32)
            norms = np.linalg.norm(feats, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1e-9, norms)
            all_features.append(feats / norms)
        return np.vstack(all_features) if all_features else np.empty((0, self.dim), dtype=np.float32)
