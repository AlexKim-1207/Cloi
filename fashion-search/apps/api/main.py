import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.cache.result_cache import init_cache_db
from src.config.settings import get_settings
from src.embedding.openclip_embed import load_clip_model
from src.llm.gemini_client import get_client
from src.search.faiss_store import FAISSStore

from .routes_search import router as search_router
from .routes_admin import router as admin_router

logger = logging.getLogger(__name__)

# ── 앱 상태 (모델 싱글턴) ──────────────────────────────────────────────────────
class AppState:
    faiss_store: FAISSStore | None = None
    clip_loaded: bool = False


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """모델 preload — 요청 시 lazy load 금지."""
    settings = get_settings()
    logger.info("[lifespan] 모델 preload 시작...")

    # 1. SQLite 캐시 DB 초기화
    init_cache_db()

    # 2. Gemini 클라이언트 초기화
    get_client()
    logger.info("[lifespan] Gemini 클라이언트 초기화 완료")

    # 3. OpenCLIP 모델 로드
    load_clip_model()
    app_state.clip_loaded = True
    logger.info("[lifespan] OpenCLIP 모델 로드 완료")

    # 4. FAISS 인덱스 로드 (있으면)
    import os
    index_path = os.path.join(settings.artifacts_dir, "catalog_vectors.index")
    if os.path.exists(index_path):
        store = FAISSStore(nprobe=settings.faiss_nprobe)
        store.load(index_path)
        app_state.faiss_store = store
        logger.info("[lifespan] FAISS 인덱스 로드 완료 (%d개)", store.size())
    else:
        logger.warning("[lifespan] FAISS 인덱스 없음 (%s). build_catalog_index.py 실행 필요.", index_path)

    app.state.app_state = app_state
    logger.info("[lifespan] 준비 완료")
    yield

    logger.info("[lifespan] 종료")


# ── FastAPI 앱 ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Fashion Search API",
    version="0.1.0",
    description="패션 이미지 유사 상품 검색 Phase 2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(search_router, prefix="/api")
app.include_router(admin_router, prefix="/admin")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "clip_loaded": app_state.clip_loaded,
        "faiss_size": app_state.faiss_store.size() if app_state.faiss_store else 0,
    }
