"""의류 영역만 추출 — 배경/피부 제거 후 색 분포 정확화."""
from io import BytesIO
from PIL import Image

try:
    from rembg import remove, new_session
    _RMBG_SESSION = new_session("u2netp")
    _RMBG_AVAILABLE = True
except ImportError:
    _RMBG_AVAILABLE = False


def remove_background(image: Image.Image) -> Image.Image:
    """배경 제거. rembg 없으면 원본 반환."""
    if not _RMBG_AVAILABLE:
        return image
    buf = BytesIO()
    image.save(buf, format='PNG')
    out = remove(buf.getvalue(), session=_RMBG_SESSION)
    return Image.open(BytesIO(out)).convert('RGB')
