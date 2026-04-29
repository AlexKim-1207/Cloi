from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_PATH), env_file_encoding="utf-8", extra="ignore")

    # Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Model weights (절대경로 기본값)
    gdino_checkpoint: str = str(_PROJECT_ROOT / "weights/groundingdino_swint_ogc.pth")
    gdino_config: str = str(_PROJECT_ROOT / "weights/GroundingDINO_SwinT_OGC.py")
    sam2_checkpoint: str = str(_PROJECT_ROOT / "weights/sam2_hiera_large.pt")
    sam2_model_cfg: str = "sam2_hiera_l.yaml"

    # Paths (절대경로 기본값)
    catalog_dir: str = str(_PROJECT_ROOT / "src/data/catalog")
    artifacts_dir: str = str(_PROJECT_ROOT / "artifacts")

    # Runtime
    faiss_nprobe: int = 10
    gemini_confidence_threshold: float = 0.70
    cache_ttl_hours: int = 24

    # OpenCLIP
    clip_model: str = "ViT-L-14"
    clip_pretrained: str = "laion2b_s32b_b82k"
    clip_batch_size: int = 32
    clip_min_similarity: float = 0.20

    # FAISS
    faiss_top_k: int = 50
    faiss_nlist_factor: float = 1.0  # nlist = max(64, int(sqrt(n) * factor))

    # Reranker top-N
    rerank_top_n: int = 20

    # Embedder selection
    embedder_name: str = "fashion_clip"
    embedder_device: str = "cpu"

    # ── v2: 네이버쇼핑 + CLIP 파이프라인 ─────────────────────────────────
    naver_client_id: str = ""
    naver_client_secret: str = ""
    search_results_per_item: int = 50
    top_k_per_category: int = 5

    # DB (검색 로그 + 인기 집계)
    db_path: str = str(_PROJECT_ROOT / "artifacts/search_logs.db")

    # Admin auth
    admin_token: str = ""

    # Runtime mode
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
