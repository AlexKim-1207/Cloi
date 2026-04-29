import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

_DB_PATH: str | None = None


def _get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        settings = get_settings()
        _DB_PATH = str(Path(settings.artifacts_dir) / "cache.db")
    return _DB_PATH


def init_cache_db() -> None:
    """캐시 DB 초기화 (테이블 생성)."""
    db_path = _get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                image_hash TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("[cache] DB 초기화 완료: %s", db_path)


def get_image_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def get_cached_result(image_hash: str) -> dict | None:
    """캐시 조회 (TTL 내 결과만 반환)."""
    settings = get_settings()
    ttl_hours = settings.cache_ttl_hours
    try:
        with sqlite3.connect(_get_db_path()) as conn:
            row = conn.execute(
                """
                SELECT result_json FROM search_cache
                WHERE image_hash = ?
                  AND datetime(created_at) > datetime('now', ? || ' hours')
                """,
                (image_hash, f"-{ttl_hours}"),
            ).fetchone()
        if row:
            logger.info("[cache] HIT: %s", image_hash[:16])
            return json.loads(row[0])
    except Exception as exc:
        logger.warning("[cache] 조회 실패: %s", exc)
    return None


def set_cached_result(image_hash: str, result: dict) -> None:
    """결과를 캐시에 저장 (upsert)."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(_get_db_path()) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO search_cache (image_hash, result_json, created_at)
                VALUES (?, ?, ?)
                """,
                (image_hash, json.dumps(result, ensure_ascii=False), now),
            )
            conn.commit()
        logger.info("[cache] SET: %s", image_hash[:16])
    except Exception as exc:
        logger.warning("[cache] 저장 실패: %s", exc)


# ── v2 비동기 캐시 API (aiosqlite) ───────────────────────────────────────────

async def get_cached(image_hash: str) -> dict | None:
    """v2 비동기 캐시 조회."""
    import aiosqlite

    settings = get_settings()
    ttl_hours = settings.cache_ttl_hours
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            async with db.execute(
                """
                SELECT result_json FROM search_cache
                WHERE image_hash = ?
                  AND datetime(created_at) > datetime('now', ? || ' hours')
                """,
                (image_hash, f"-{ttl_hours}"),
            ) as cursor:
                row = await cursor.fetchone()
        if row:
            logger.info("[cache] HIT (async): %s", image_hash[:16])
            return json.loads(row[0])
    except Exception as exc:
        logger.warning("[cache] async 조회 실패: %s", exc)
    return None


async def set_cached(image_hash: str, data: dict) -> None:
    """v2 비동기 캐시 저장."""
    import aiosqlite

    try:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO search_cache (image_hash, result_json, created_at)
                VALUES (?, ?, ?)
                """,
                (image_hash, json.dumps(data, ensure_ascii=False), now),
            )
            await db.commit()
        logger.info("[cache] SET (async): %s", image_hash[:16])
    except Exception as exc:
        logger.warning("[cache] async 저장 실패: %s", exc)
