import numpy as np
import torch
from PIL import Image

from src.embedding.embedder_base import ImageEmbedder


class OpenCLIPEmbedder(ImageEmbedder):
    name = "openclip_vitl14"
    dim = 768

    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self._model = None
        self._preprocess = None

    def load(self) -> None:
        if self._model is not None:
            return
        import open_clip  # type: ignore
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            "ViT-L-14", pretrained="laion2b_s32b_b82k"
        )
        self._model.eval()

    def embed(self, images: list[Image.Image]) -> np.ndarray:
        if self._model is None:
            self.load()
        all_features: list[np.ndarray] = []
        for i in range(0, len(images), self.batch_size):
            batch = images[i : i + self.batch_size]
            tensors = torch.stack([self._preprocess(img) for img in batch])
            with torch.no_grad():
                feats = self._model.encode_image(tensors).cpu().numpy().astype(np.float32)
            norms = np.linalg.norm(feats, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1e-9, norms)
            all_features.append(feats / norms)
        return np.vstack(all_features) if all_features else np.empty((0, self.dim), dtype=np.float32)
