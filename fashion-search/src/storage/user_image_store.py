"""GCS 유저 이미지 저장 — fire-and-forget."""
import json
from datetime import datetime
from typing import Optional

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
