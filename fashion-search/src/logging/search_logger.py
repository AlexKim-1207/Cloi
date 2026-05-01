"""검색 로그 저장 + 클릭 기록 + 인기 TOP 10 집계 (aiosqlite 비동기)."""
import json
import logging
from pathlib import Path

import aiosqlite

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

_NEW_CLICK_COLUMNS = [
    ("clicked_product_title", "TEXT"),
    ("clicked_product_image_url", "TEXT"),
    ("clicked_product_price", "INTEGER"),
    ("final_score", "REAL"),
    ("rank_position", "INTEGER"),
    ("mood_label", "TEXT"),
    ("session_id", "TEXT"),
    ("visual_similarity", "REAL"),
    ("mood_alignment", "REAL"),
    ("naver_rank_score", "REAL"),
]


def _get_db_path() -> str:
    return get_settings().db_path


async def init_db() -> None:
    """search_logs, product_clicks, product_impressions 테이블 생성 + 마이그레이션."""
    db_path = _get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS search_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                image_hash   TEXT NOT NULL,
                style_context TEXT NOT NULL,
                items_searched TEXT NOT NULL,
                results      TEXT NOT NULL,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS product_clicks (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                image_hash              TEXT NOT NULL,
                product_id              TEXT NOT NULL,
                category                TEXT NOT NULL,
                created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS product_impressions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                image_hash      TEXT NOT NULL,
                product_id      TEXT NOT NULL,
                tab_id          TEXT,
                rank_position   INTEGER,
                visual_similarity REAL,
                mood_alignment  REAL,
                match_score     REAL,
                clicked         INTEGER DEFAULT 0,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_search_logs_hash
                ON search_logs (image_hash);

            CREATE INDEX IF NOT EXISTS idx_clicks_product
                ON product_clicks (product_id);

            CREATE INDEX IF NOT EXISTS idx_impressions_session
                ON product_impressions (session_id);

            CREATE INDEX IF NOT EXISTS idx_impressions_image
                ON product_impressions (image_hash);
            """
        )

        # product_clicks 신규 컬럼 마이그레이션
        for col_name, col_type in _NEW_CLICK_COLUMNS:
            try:
                await db.execute(
                    f"ALTER TABLE product_clicks ADD COLUMN {col_name} {col_type}"
                )
            except Exception:
                pass

        await db.commit()
    logger.info("[search_logger] DB 초기화 완료: %s", db_path)


async def log_search(
    image_hash: str,
    style_context,
    results: dict,
) -> None:
    flat_results: list = []
    if hasattr(style_context, 'detected_items'):
        for tab_id, items in results.items():
            for p in items:
                flat_results.append({
                    "product_id": p.get("product_id", ""),
                    "category": p.get("category", tab_id),
                    "title": p.get("title", ""),
                    "price": p.get("price", 0),
                    "image_url": p.get("image_url", ""),
                    "link": p.get("link", ""),
                    "similarity_score": p.get("similarity_score", 0.0),
                    "click": False,
                })
        items_searched = [item.tab_id for item in style_context.detected_items]
        style_json = style_context.model_dump_json()
    else:
        for items in results.values():
            for p in items:
                flat_results.append({
                    "product_id": p.get("product_id", ""),
                    "category": p.get("category", ""),
                    "title": p.get("title", ""),
                    "price": p.get("price", 0),
                    "image_url": p.get("image_url", ""),
                    "link": p.get("link", ""),
                    "similarity_score": p.get("similarity_score", 0.0),
                    "click": False,
                })
        items_searched = [item.category for item in style_context.items]
        style_json = style_context.model_dump_json()

    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                """
                INSERT INTO search_logs (image_hash, style_context, items_searched, results)
                VALUES (?, ?, ?, ?)
                """,
                (
                    image_hash,
                    style_json,
                    json.dumps(items_searched, ensure_ascii=False),
                    json.dumps(flat_results, ensure_ascii=False),
                ),
            )
            await db.commit()
        logger.debug("[search_logger] 로그 저장: %s...", image_hash[:16])
    except Exception as exc:
        logger.warning("[search_logger] 로그 저장 실패: %s", exc)


async def log_impressions(
    session_id: str,
    image_hash: str,
    products: list[dict],
) -> None:
    """검색 결과 노출 시 모든 상품을 impression으로 기록 (negative pair 데이터)."""
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            for p in products:
                await db.execute(
                    """
                    INSERT INTO product_impressions (
                        session_id, image_hash, product_id, tab_id, rank_position,
                        visual_similarity, mood_alignment, match_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id, image_hash,
                        p.get('product_id', ''),
                        p.get('tab_id', ''),
                        p.get('rank_position', 0),
                        p.get('_visual_sim', 0.0),
                        p.get('_mood_align', 0.0),
                        p.get('match_score', 0.0),
                    ),
                )
            await db.commit()
    except Exception as exc:
        logger.warning("[search_logger] impression 기록 실패: %s", exc)


async def mark_impression_clicked(session_id: str, product_id: str) -> None:
    """클릭 시 해당 impression 레코드의 clicked=1로 업데이트."""
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                """
                UPDATE product_impressions
                SET clicked = 1
                WHERE session_id = ? AND product_id = ?
                """,
                (session_id, product_id),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("[search_logger] impression 업데이트 실패: %s", exc)


async def log_click(image_hash: str, product_id: str, category: str) -> None:
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                "INSERT INTO product_clicks (image_hash, product_id, category) VALUES (?, ?, ?)",
                (image_hash, product_id, category),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("[search_logger] 클릭 기록 실패: %s", exc)


async def log_click_v2(
    image_hash: str,
    product_id: str,
    category: str,
    product_title: str = "",
    product_image_url: str = "",
    product_price: int = 0,
    final_score: float = 0.0,
    rank_position: int = 0,
    mood_label: str = "",
    session_id: str = "",
) -> None:
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                """
                INSERT INTO product_clicks (
                    image_hash, product_id, category,
                    clicked_product_title, clicked_product_image_url,
                    clicked_product_price, final_score, rank_position,
                    mood_label, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_hash, product_id, category,
                    product_title, product_image_url,
                    product_price, final_score, rank_position,
                    mood_label, session_id,
                ),
            )
            await db.commit()
        logger.debug("[search_logger] 클릭 v2 기록: %s / %s", product_id, category)
    except Exception as exc:
        logger.warning("[search_logger] 클릭 v2 기록 실패: %s", exc)


async def get_popular_items(
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    base_query = """
        SELECT
            json_extract(r.value, '$.product_id') AS product_id,
            json_extract(r.value, '$.category')   AS category,
            json_extract(r.value, '$.title')       AS title,
            json_extract(r.value, '$.image_url')   AS image_url,
            COUNT(DISTINCT sl.id)                  AS search_count,
            COUNT(DISTINCT pc.id)                  AS click_count,
            ROUND(
                CAST(COUNT(DISTINCT pc.id) AS FLOAT)
                / NULLIF(COUNT(DISTINCT sl.id), 0),
                3
            ) AS ctr
        FROM search_logs sl
        CROSS JOIN json_each(sl.results) r
        LEFT JOIN product_clicks pc
            ON pc.product_id = json_extract(r.value, '$.product_id')
        WHERE json_extract(r.value, '$.product_id') IS NOT NULL
    """
    params: list = []

    if category:
        base_query += " AND json_extract(r.value, '$.category') = ?"
        params.append(category)

    base_query += """
        GROUP BY json_extract(r.value, '$.product_id')
        HAVING COUNT(DISTINCT sl.id) >= 3
        ORDER BY ctr DESC, search_count DESC
        LIMIT ?
    """
    params.append(limit)

    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(base_query, params) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("[search_logger] 인기 조회 실패: %s", exc)
        return []
