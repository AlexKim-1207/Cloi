"""v2 스모크 테스트 - 전체 파이프라인 latency 측정.

Usage:
    # 실제 서버 테스트
    python -m scripts.smoke_test --base-url http://localhost:8000 --images tests/fixtures/images

    # Mock 모드 (API 키 없이 파이프라인 로직만 테스트)
    python -m scripts.smoke_test --mock

목표 latency:
    Gemini 분석:                 < 3초
    네이버쇼핑 병렬 검색 (4개):  < 2초
    CLIP 필터 (200개 썸네일):    < 5초
    전체 파이프라인:             < 10초
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Mock 데이터 ───────────────────────────────────────────────────────────────

MOCK_STYLE_CONTEXT = {
    "overall_style": "캐주얼 스트릿",
    "mood_tags": ["스트릿", "빈티지"],
    "items": [
        {"category": "후드티", "color": "그레이", "fit": "오버사이즈"},
        {"category": "와이드팬츠", "color": "블랙"},
        {"category": "스니커즈", "color": "화이트"},
    ],
    "confidence": 0.92,
}

MOCK_PRODUCT = {
    "product_id": "mock_001",
    "title": "무신사 스탠다드 오버사이즈 후드티",
    "price": 39000,
    "image_url": "",
    "link": "https://www.musinsa.com",
    "platform": "무신사",
    "category": "후드티",
    "similarity_score": 0.87,
}


def _make_mock_response() -> dict:
    return {
        "style_context": MOCK_STYLE_CONTEXT,
        "results": {
            "후드티": [MOCK_PRODUCT],
            "와이드팬츠": [{**MOCK_PRODUCT, "product_id": "mock_002", "category": "와이드팬츠"}],
        },
        "cached": False,
        "latency_ms": 1234,
    }


# ── 실서버 테스트 ─────────────────────────────────────────────────────────────

def _load_test_images(images_dir: str) -> list[tuple[str, bytes]]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    img_dir = Path(images_dir)
    if not img_dir.exists():
        print(f"[smoke_test] 이미지 디렉토리 없음: {images_dir}")
        return []
    paths = sorted(p for p in img_dir.rglob("*") if p.suffix.lower() in exts)[:3]
    return [(str(p), p.read_bytes()) for p in paths]


def _run_health_check(base_url: str) -> bool:
    try:
        import httpx
        r = httpx.get(f"{base_url}/health", timeout=10)
        data = r.json()
        print(f"[health] {r.status_code}: {json.dumps(data, ensure_ascii=False)}")
        return r.status_code == 200
    except Exception as exc:
        print(f"[health] 실패: {exc}")
        return False


def _run_search(base_url: str, image_bytes: bytes, image_name: str, idx: int) -> None:
    try:
        import httpx

        start = time.perf_counter()
        r = httpx.post(
            f"{base_url}/api/search",
            files={"file": (image_name, image_bytes, "image/jpeg")},
            timeout=60.0,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if r.status_code == 200:
            data = r.json()
            style = data["style_context"]
            results = data["results"]
            total_items = sum(len(v) for v in results.values())

            print(f"\n[{idx}] {image_name}")
            print(f"     스타일: {style['overall_style']} (confidence={style['confidence']:.2f})")
            print(f"     아이템: {[i['category'] for i in style['items']]}")
            print(f"     결과:   카테고리 {len(results)}개 / 총 상품 {total_items}개")
            print(f"     레이턴시: {elapsed_ms}ms (캐시={data['cached']})")

            # 목표 latency 체크
            target_ms = 10_000
            status = "[OK]" if elapsed_ms <= target_ms else f"[초과 목표 {target_ms}ms]"
            print(f"     latency 체크: {status}")

            # 카테고리별 TOP 1 출력
            for category, items in results.items():
                if items:
                    top = items[0]
                    print(f"     [{category}] 1위: {top['title'][:30]} - {top['price']:,}원 (sim={top['similarity_score']:.3f})")
        else:
            print(f"\n[{idx}] {image_name} -> HTTP {r.status_code}: {r.text[:300]}")

    except Exception as exc:
        print(f"\n[{idx}] {image_name} -> 오류: {exc}")


def run_live(base_url: str, images_dir: str) -> None:
    print(f"\n{'='*50}")
    print(f"  Fashion Search v2 - Smoke Test (Live)")
    print(f"  Target: {base_url}")
    print(f"{'='*50}\n")

    if not _run_health_check(base_url):
        print("[smoke_test] 서버 응답 없음. 종료.")
        sys.exit(1)

    images = _load_test_images(images_dir)
    if not images:
        print("[smoke_test] 테스트 이미지 없음. --images 경로 확인 필요.")
        print("  예시: python -m scripts.smoke_test --mock  (mock 모드)")
        sys.exit(1)

    print(f"\n[smoke_test] {len(images)}장 테스트 시작\n")
    latencies: list[int] = []

    for i, (path, img_bytes) in enumerate(images, 1):
        start = time.perf_counter()
        _run_search(base_url, img_bytes, Path(path).name, i)
        latencies.append(int((time.perf_counter() - start) * 1000))

    if latencies:
        print(f"\n{'='*50}")
        print(f"  평균 {sum(latencies)//len(latencies)}ms | 최소 {min(latencies)}ms | 최대 {max(latencies)}ms")


def run_mock() -> None:
    """API 키 없이 파이프라인 모듈 직접 테스트."""
    print(f"\n{'='*50}")
    print(f"  Fashion Search v2 - Smoke Test (Mock)")
    print(f"{'='*50}\n")

    stages = [
        ("Gemini 스타일 분석 (mock)", 0.05),
        ("네이버쇼핑 병렬 검색 (mock, 3개 아이템)", 0.08),
        ("CLIP 유사도 필터 (mock, 150개 썸네일)", 0.12),
    ]
    results: dict[str, int] = {}

    for stage_name, simulated_secs in stages:
        start = time.perf_counter()
        time.sleep(simulated_secs)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        results[stage_name] = elapsed_ms
        print(f"  [OK] {stage_name}: {elapsed_ms}ms")

    total = sum(results.values())
    print(f"\n  전체 파이프라인: {total}ms")

    response = _make_mock_response()
    print(f"\n[mock response 예시]")
    print(json.dumps(response, ensure_ascii=False, indent=2)[:600] + "...")

    print(f"\n{'='*50}")
    print("  목표 latency 체크 (mock - 실제와 다를 수 있음):")
    print(f"  Gemini < 3000ms:          {'[OK]' if results[stages[0][0]] < 3000 else '[NG]'}")
    print(f"  Naver  < 2000ms:          {'[OK]' if results[stages[1][0]] < 2000 else '[NG]'}")
    print(f"  CLIP   < 5000ms:          {'[OK]' if results[stages[2][0]] < 5000 else '[NG]'}")
    print(f"  Total  < 10000ms:         {'[OK]' if total < 10000 else '[NG]'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fashion Search v2 스모크 테스트")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API 서버 URL")
    parser.add_argument("--images", default="tests/fixtures/images", help="테스트 이미지 디렉토리")
    parser.add_argument("--mock", action="store_true", help="Mock 모드 (API 키 불필요)")
    args = parser.parse_args()

    if args.mock:
        run_mock()
    else:
        run_live(args.base_url, args.images)


if __name__ == "__main__":
    main()
