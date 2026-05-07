"""네이버 쇼핑 API로 패션 카탈로그 자동 수집.

Usage:
    python -m scripts.collect_catalog \
        --naver-client-id YOUR_ID \
        --naver-client-secret YOUR_SECRET \
        [--per-category 100] [--catalog-dir src/data/catalog]

남성/여성 의류 전 카테고리 상품 이미지 + 메타데이터를 수집해
catalog_dir/images/ 에 이미지 저장, catalog_dir/meta.json 에 메타데이터 저장.
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("collect_catalog")

NAVER_API_URL = "https://openapi.naver.com/v1/search/shop.json"

CATEGORIES = [
    # 여성
    "여성 티셔츠", "여성 블라우스", "여성 원피스", "여성 스커트",
    "여성 청바지", "여성 슬랙스", "여성 레깅스", "여성 반바지",
    "여성 재킷", "여성 코트", "여성 패딩", "여성 가디건",
    "여성 후드티", "여성 맨투맨", "여성 니트", "여성 점프수트",
    # 남성
    "남성 티셔츠", "남성 셔츠", "남성 청바지", "남성 슬랙스",
    "남성 반바지", "남성 재킷", "남성 코트", "남성 패딩",
    "남성 후드티", "남성 맨투맨", "남성 니트", "남성 트레이닝복",
]


def search_naver(query: str, client_id: str, client_secret: str, display: int = 100, start: int = 1) -> list[dict]:
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": query, "display": display, "start": start, "sort": "sim"}
    try:
        r = httpx.get(NAVER_API_URL, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        return items
    except Exception as e:
        logger.warning("네이버 검색 실패 [%s]: %s", query, e)
        return []


def download_image(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "image" not in content_type:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except Exception:
        return False


def strip_html(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html)


def main() -> None:
    parser = argparse.ArgumentParser(description="네이버 쇼핑 카탈로그 수집")
    parser.add_argument("--naver-client-id", default=os.getenv("NAVER_CLIENT_ID"), required=False)
    parser.add_argument("--naver-client-secret", default=os.getenv("NAVER_CLIENT_SECRET"), required=False)
    parser.add_argument("--per-category", type=int, default=100, help="카테고리당 수집 수 (최대 100)")
    parser.add_argument("--catalog-dir", default="src/data/catalog", help="저장 디렉토리")
    args = parser.parse_args()

    if not args.naver_client_id or not args.naver_client_secret:
        logger.error(".env 파일에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 을 설정하거나 인수로 전달하세요.")
        sys.exit(1)

    catalog_dir = Path(args.catalog_dir)
    images_dir = catalog_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    meta_path = catalog_dir / "meta.json"

    # 기존 메타 로드 (이어서 실행 지원)
    existing_meta: dict[str, dict] = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            existing_meta = json.load(f)
    logger.info("기존 상품 수: %d", len(existing_meta))

    meta = dict(existing_meta)
    total_downloaded = 0
    total_skipped = 0

    for category in CATEGORIES:
        logger.info("수집 중: %s", category)
        items = search_naver(category, args.naver_client_id, args.naver_client_secret, display=min(args.per_category, 100))

        for item in items:
            product_id = item.get("productId") or item.get("mallProductId")
            if not product_id:
                continue
            product_id = f"naver_{product_id}"

            image_url = item.get("image", "")
            if not image_url:
                continue

            # 이미지 확장자 결정
            ext = ".jpg"
            if ".png" in image_url:
                ext = ".png"
            elif ".webp" in image_url:
                ext = ".webp"

            dest = images_dir / f"{product_id}{ext}"

            if product_id in meta:
                total_skipped += 1
                continue

            ok = download_image(image_url, dest)
            if not ok:
                continue

            meta[product_id] = {
                "product_id": product_id,
                "path": str(dest),
                "name": strip_html(item.get("title", "")),
                "brand": item.get("brand", ""),
                "price": int(item.get("lprice", 0) or 0),
                "category": category,
                "shop_url": item.get("link", ""),
                "mall_name": item.get("mallName", ""),
                "image_url": image_url,
            }
            total_downloaded += 1

            if total_downloaded % 50 == 0:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                logger.info("중간 저장 — 총 %d개", len(meta))

            time.sleep(0.05)  # API 레이트 리밋 방지

        time.sleep(0.3)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info("=== 수집 완료 ===")
    logger.info("새로 다운로드: %d개", total_downloaded)
    logger.info("이미 존재(스킵): %d개", total_skipped)
    logger.info("총 카탈로그: %d개", len(meta))
    logger.info("다음 단계: python -m scripts.build_catalog_index")


if __name__ == "__main__":
    main()
