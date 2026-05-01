"""GCS 세션 스냅샷 + SQLite impression/click → 학습 데이터셋."""
import asyncio
import json
from pathlib import Path

import aiosqlite


async def export_training_data(
    output_path: str,
    min_clicks_per_session: int = 1,
) -> dict:
    """모든 세션 데이터를 학습 가능한 jsonl로 export.

    각 라인:
    {
        "query_image_hash": "abc...",
        "positives": ["product_id_1", ...],
        "negatives": ["product_id_2", ...],
        "session_id": "...",
    }
    """
    db_path = "fashion-search/data/search.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        query = """
        SELECT
            i.session_id,
            i.image_hash,
            i.product_id,
            i.tab_id,
            i.rank_position,
            i.match_score,
            i.clicked
        FROM product_impressions i
        WHERE i.session_id IN (
            SELECT session_id
            FROM product_impressions
            WHERE clicked = 1
            GROUP BY session_id
            HAVING COUNT(*) >= ?
        )
        ORDER BY i.session_id, i.rank_position
        """

        async with db.execute(query, (min_clicks_per_session,)) as cursor:
            rows = await cursor.fetchall()

    sessions: dict = {}
    for row in rows:
        sid = row['session_id']
        if sid not in sessions:
            sessions[sid] = {
                'session_id': sid,
                'image_hash': row['image_hash'],
                'positives': [],
                'negatives': [],
            }
        if row['clicked']:
            sessions[sid]['positives'].append(row['product_id'])
        else:
            sessions[sid]['negatives'].append(row['product_id'])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for sess in sessions.values():
            f.write(json.dumps(sess, ensure_ascii=False) + '\n')

    return {
        'sessions_exported': len(sessions),
        'total_positives': sum(len(s['positives']) for s in sessions.values()),
        'total_negatives': sum(len(s['negatives']) for s in sessions.values()),
    }


if __name__ == "__main__":
    stats = asyncio.run(export_training_data('training/data/raw/sessions.jsonl'))
    print(f"Exported: {stats}")
