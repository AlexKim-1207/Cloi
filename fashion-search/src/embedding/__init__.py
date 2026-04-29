from src.embedding.embedder_base import ImageEmbedder
from src.embedding.openclip_embedder import OpenCLIPEmbedder
from src.embedding.fashion_clip_embedder import FashionCLIPEmbedder
from src.embedding.marqo_siglip_embedder import MarqoSigLIPEmbedder


def get_embedder(name: str) -> ImageEmbedder:
    if name == "openclip_vitl14":
        return OpenCLIPEmbedder()
    if name == "fashion_clip":
        return FashionCLIPEmbedder()
    if name == "marqo_fashion_siglip":
        return MarqoSigLIPEmbedder()
    raise ValueError(f"Unknown embedder: {name}")


__all__ = [
    "ImageEmbedder",
    "OpenCLIPEmbedder",
    "FashionCLIPEmbedder",
    "MarqoSigLIPEmbedder",
    "get_embedder",
]
