import logging
import os

# OpenMP 중복 라이브러리 충돌 방지 (FAISS + PyTorch)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from src.cache.result_cache import init_cache_db
from src.config.settings import get_settings
from src.embedding import ImageEmbedder, get_embedder
from src.embedding.fashion_clip_embedder import FashionCLIPEmbedder
from src.llm.gemini_client import get_client
from src.logging.search_logger import init_db as init_search_db
from src.ranking.attribute_classifier import AttributeClassifier
from src.search.faiss_store import FAISSStore

from .routes_search import router as search_router
from .routes_admin import router as admin_router

logger = logging.getLogger(__name__)


class AppState:
    faiss_store: FAISSStore | None = None
    embedder: ImageEmbedder | None = None
    attribute_classifier: AttributeClassifier | None = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """모델 preload + DB 초기화."""
    settings = get_settings()
    logger.info("[lifespan] 시작...")

    # 1. SQLite 캐시 DB 초기화
    init_cache_db()

    # 2. 검색 로그 DB 초기화
    await init_search_db()

    # 3. Gemini 클라이언트 초기화
    get_client()
    logger.info("[lifespan] Gemini 클라이언트 초기화 완료")

    # 4. Embedder preload
    embedder = get_embedder(settings.embedder_name)
    embedder.load()
    app_state.embedder = embedder
    logger.info("[lifespan] Embedder 로드 완료: %s", settings.embedder_name)

    # 5. AttributeClassifier (FashionCLIP 인스턴스 재사용)
    if isinstance(embedder, FashionCLIPEmbedder):
        app_state.attribute_classifier = AttributeClassifier(embedder)
        logger.info("[lifespan] AttributeClassifier 초기화 완료")
    else:
        logger.warning("[lifespan] FashionCLIPEmbedder 아님 — AttributeClassifier 비활성화")

    # 6. FAISS 인덱스 로드 (admin 라우터용 — 없으면 경고만)
    index_path = str(PROJECT_ROOT / settings.artifacts_dir / "catalog.index")
    if os.path.exists(index_path):
        store = FAISSStore(nprobe=settings.faiss_nprobe)
        store.load(index_path)
        app_state.faiss_store = store
        logger.info("[lifespan] FAISS 인덱스 로드 완료 (%d개)", store.size())
    else:
        logger.warning("[lifespan] FAISS 인덱스 없음 — admin 카탈로그 기능 비활성화")

    app.state.app_state = app_state
    logger.info("[lifespan] 준비 완료")
    yield
    logger.info("[lifespan] 종료")


_settings = get_settings()

_ALLOWED_ORIGINS = [
    "https://cloi.pages.dev",
    "https://cloi-api.kyoung361207.workers.dev",
    "http://localhost:5173",
    "http://localhost:3000",
]

app = FastAPI(
    title="Fashion Search API v3",
    version="3.0.0",
    description="멀티아이템 탐지 + FashionCLIP 속성추출 + 무드기반 소팅",
    lifespan=lifespan,
    docs_url="/docs" if _settings.debug else None,
    redoc_url="/redoc" if _settings.debug else None,
    openapi_url="/openapi.json" if _settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(search_router, prefix="/api")
app.include_router(admin_router, prefix="/admin")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "embedder": app_state.embedder.name if app_state.embedder else None,
        "attribute_classifier": app_state.attribute_classifier is not None,
        "faiss_size": app_state.faiss_store.size() if app_state.faiss_store else 0,
    }
