"""단일 상품을 카탈로그에 증분 추가.

Usage:
    python -m scripts.add_catalog_item \
        --image path/to/image.jpg \
        --product-id PROD_001 \
        --name "흰색 오버핏 티셔츠" \
        --brand "무신사 스탠다드" \
        --price 29000 \
        --category top \
        --shop-url "https://..."
        --base-url http://localhost:8000
"""
import argparse
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="카탈로그 단일 상품 추가")
    parser.add_argument("--image", required=True, help="이미지 파일 경로")
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--brand", default="")
    parser.add_argument("--price", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument("--shop-url", default="")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    try:
        import httpx
    except ImportError:
        print("httpx 패키지 필요: pip install httpx")
        sys.exit(1)

    image_bytes = Path(args.image).read_bytes()
    payload = {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "mime_type": "image/jpeg",
        "product_id": args.product_id,
        "name": args.name,
        "brand": args.brand,
        "price": args.price,
        "category": args.category,
        "shop_url": args.shop_url,
    }

    r = httpx.post(f"{args.base_url}/admin/catalog/add", json=payload, timeout=60)
    if r.status_code == 200:
        data = r.json()
        print(f"추가 완료: {data['product_id']} (총 {data['total']}개)")
    else:
        print(f"실패 HTTP {r.status_code}: {r.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
