from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Gemini
    google_api_key: str = ""

    # Model weights
    gdino_checkpoint: str = "weights/groundingdino_swint_ogc.pth"
    gdino_config: str = "weights/GroundingDINO_SwinT_OGC.py"
    sam2_checkpoint: str = "weights/sam2_hiera_large.pt"
    sam2_model_cfg: str = "sam2_hiera_l.yaml"

    # Paths
    catalog_dir: str = "src/data/catalog"
    artifacts_dir: str = "artifacts"

    # Runtime
    faiss_nprobe: int = 10
    gemini_confidence_threshold: float = 0.70
    cache_ttl_hours: int = 24

    # OpenCLIP
    clip_model: str = "ViT-L-14"
    clip_pretrained: str = "laion2b_s32b_b82k"
    clip_batch_size: int = 32

    # FAISS
    faiss_top_k: int = 50
    faiss_nlist_factor: float = 1.0  # nlist = max(64, int(sqrt(n) * factor))

    # Reranker top-N
    rerank_top_n: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
