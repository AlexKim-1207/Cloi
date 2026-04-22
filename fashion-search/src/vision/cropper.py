"""bbox → crop PNG 유틸리티."""
import io
from pathlib import Path

from PIL import Image


def crop_to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    """PIL Image → bytes 변환."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def save_crop(image: Image.Image, output_path: str | Path) -> None:
    """crop 이미지를 파일로 저장."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output_path), format="PNG")
