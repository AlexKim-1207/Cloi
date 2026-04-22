import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import google.genai as genai
from google.genai import types

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def _make_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.google_api_key)


# 모듈 레벨 싱글턴 클라이언트 (lifespan에서 초기화)
_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)
async def generate_with_retry(
    prompt: str,
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    model: str = "gemini-2.5-flash",
) -> str | None:
    """Gemini API 호출 (tenacity 재시도 포함).

    Returns:
        응답 텍스트 또는 None (최대 재시도 초과 시)
    """
    try:
        client = get_client()
        parts: list = [prompt]
        if image_bytes is not None:
            parts = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ]
        response = client.models.generate_content(
            model=model,
            contents=parts,
        )
        return response.text
    except Exception as exc:
        logger.warning("[gemini_client] generate_with_retry 실패: %s", exc)
        raise
