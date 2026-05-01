"""GCS 유저 이미지 저장 — fire-and-forget."""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from google.cloud import storage  # type: ignore
    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False


class UserImageStore:
    def __init__(self, bucket_name: str = 'cloi-user-images'):
        self.enabled = _GCS_AVAILABLE
        if not self.enabled:
            return
        try:
            self.client = storage.Client()
            self.bucket = self.client.bucket(bucket_name)
        except Exception:
            self.enabled = False

    async def save_async(
        self,
        image_bytes: bytes,
        image_hash: str,
        style_context: dict,
        attributes: dict,
        clip_embedding: Optional[list] = None,
    ) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            now = datetime.utcnow()
            prefix = f'user-images/{now.year}/{now.month:02d}/{now.day:02d}'

            img_blob = self.bucket.blob(f'{prefix}/{image_hash}.jpg')
            img_blob.upload_from_string(image_bytes, content_type='image/jpeg')

            meta = {
                'hash': image_hash,
                'timestamp': now.isoformat(),
                'style_context': style_context,
                'attributes': attributes,
                'embedding': clip_embedding,
            }
            meta_blob = self.bucket.blob(f'{prefix}/{image_hash}.json')
            meta_blob.upload_from_string(
                json.dumps(meta, ensure_ascii=False),
                content_type='application/json',
            )

            return f'gs://cloi-user-images/{prefix}/{image_hash}.jpg'
        except Exception:
            return None

    async def save_session_snapshot(
        self,
        image_hash: str,
        session_id: str,
        products_shown: list[dict],
        query_attributes: dict,
    ) -> None:
        """검색 세션 전체 스냅샷 저장.

        Naver URL 만료 대비 + impression-level 학습 데이터 확보.
        클릭 안 된 상품(negative)도 모두 저장하여 contrastive learning 가능.

        저장 구조:
            gs://cloi-user-images/sessions/{YYYY/MM/DD}/{image_hash}.json
        """
        if not self.enabled:
            return
        try:
            now = datetime.utcnow()
            prefix = f'sessions/{now.year}/{now.month:02d}/{now.day:02d}'

            snapshot = {
                'session_id': session_id,
                'image_hash': image_hash,
                'timestamp': now.isoformat(),
                'query_attributes': query_attributes,
                'products_shown': products_shown,
            }

            blob = self.bucket.blob(f'{prefix}/{image_hash}.json')
            blob.upload_from_string(
                json.dumps(snapshot, ensure_ascii=False),
                content_type='application/json',
            )
        except Exception as e:
            logger.warning("[UserImageStore] 세션 스냅샷 저장 실패: %s", e)

    async def cache_product_thumbnail(
        self,
        product_id: str,
        image_bytes: bytes,
    ) -> Optional[str]:
        """클릭된 상품 썸네일 캐시 저장 (Naver URL 만료 대비)."""
        if not self.enabled:
            return None
        try:
            pid_hash = hashlib.md5(product_id.encode()).hexdigest()[:16]
            blob = self.bucket.blob(f'product-thumbs/{pid_hash}.jpg')

            if blob.exists():
                return f'gs://cloi-user-images/product-thumbs/{pid_hash}.jpg'

            blob.upload_from_string(image_bytes, content_type='image/jpeg')
            return f'gs://cloi-user-images/product-thumbs/{pid_hash}.jpg'
        except Exception:
            return None
