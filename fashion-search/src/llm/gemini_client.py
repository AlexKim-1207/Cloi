import logging

from src.config.settings import get_settings
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import google.genai as genai
from google.genai import types


def _is_transient(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("503", "service unavailable", "high demand", "resource_exhausted", "429", "unavailable"))

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
    retry=retry_if_exception(_is_transient),
    reraise=False,
)
async def generate_with_retry(
    prompt: str,
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    model: str = "",
) -> str | None:
    """Gemini API 호출 (tenacity 재시도 포함).

    Returns:
        응답 텍스트 또는 None (최대 재시도 초과 시)
    """
    try:
        client = get_client()
        resolved_model = model or get_settings().gemini_model
        parts: list = [types.Part.from_text(text=prompt)]
        if image_bytes is not None:
            parts = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=prompt),
            ]
        response = client.models.generate_content(
            model=resolved_model,
            contents=parts,
        )
        return response.text
    except Exception as exc:
        logger.warning("[gemini_client] generate_with_retry 실패: %s", exc)
        raise
