"""스모크 테스트 — API 기본 동작 + 레이턴시 측정.

Usage:
    python -m scripts.smoke_test --base-url http://localhost:8000 [--images DIR]

3장의 이미지로 /api/search 엔드포인트를 호출하고
각 요청의 레이턴시와 응답 결과를 출력.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_test_images(images_dir: str) -> list[tuple[str, bytes]]:
    """테스트 이미지 디렉토리에서 최대 3장 로드."""
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    img_dir = Path(images_dir)
    paths = sorted(p for p in img_dir.rglob("*") if p.suffix.lower() in exts)[:3]
    if not paths:
        print(f"[smoke_test] 이미지 없음: {images_dir}")
        sys.exit(1)
    return [(str(p), p.read_bytes()) for p in paths]


def run_test(base_url: str, images: list[tuple[str, bytes]]) -> None:
    try:
        import httpx
    except ImportError:
        print("[smoke_test] httpx 패키지 필요: pip install httpx")
        sys.exit(1)

    print(f"\n=== Fashion Search Smoke Test ===")
    print(f"Target: {base_url}")
    print(f"Images: {len(images)}장\n")

    # Health check
    try:
        r = httpx.get(f"{base_url}/health", timeout=10)
        print(f"[health] {r.status_code}: {r.json()}\n")
    except Exception as e:
        print(f"[health] 실패: {e}")
        sys.exit(1)

    latencies = []
    for i, (path, img_bytes) in enumerate(images, 1):
        img_b64 = base64.b64encode(img_bytes).decode()
        payload = {"image_base64": img_b64, "mime_type": "image/jpeg", "top_k": 10}

        start = time.perf_counter()
        try:
            r = httpx.post(f"{base_url}/api/search", json=payload, timeout=120)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

            if r.status_code == 200:
                data = r.json()
                print(f"[{i}] {Path(path).name}")
                print(f"     ✓ 결과 {data['total']}개 | 레이턴시 {elapsed:.0f}ms | 캐시={data.get('cached', False)}")
                if data["results"]:
                    top = data["results"][0]
                    print(f"     상위 1위: {top['product_id']} (score={top['final_score']})")
            else:
                print(f"[{i}] {Path(path).name} — HTTP {r.status_code}: {r.text[:200]}")

        except Exception as e:
            print(f"[{i}] {Path(path).name} — 오류: {e}")

        print()

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"=== 레이턴시 통계 ===")
        print(f"평균: {avg:.0f}ms | 최소: {min(latencies):.0f}ms | 최대: {max(latencies):.0f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fashion Search 스모크 테스트")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API 베이스 URL")
    parser.add_argument("--images", default="tests/fixtures/images", help="테스트 이미지 디렉토리")
    args = parser.parse_args()

    images = load_test_images(args.images)
    run_test(args.base_url, images)


if __name__ == "__main__":
    main()
