"""Track A 라이브 QA — Worker /api/analyze 직접 호출 + _source 확인."""
import base64
import json
import sys
import time
from pathlib import Path

import urllib.request

URL = 'https://cloi-api.kyoung361207.workers.dev/api/analyze'

# 카탈로그 이미지 5개 사용 (테스트 전용)
CATALOG_DIR = Path(__file__).parent.parent / 'src' / 'data' / 'catalog'
IMAGE_FILES = sorted(CATALOG_DIR.glob('p0*.jpg'))[:5]

if not IMAGE_FILES:
    print("ERROR: No catalog images found", file=sys.stderr)
    sys.exit(1)

results = []
for img_path in IMAGE_FILES:
    with open(img_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()

    data = json.dumps({'imageBase64': b64, 'mimeType': 'image/jpeg'}).encode()
    req = urllib.request.Request(
        URL,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Origin': 'https://cloi.pages.dev',
            'User-Agent': 'Mozilla/5.0 (QA-Test)',
        },
        method='POST',
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            j = json.loads(resp.read().decode())
    except Exception as e:
        print(f"\n=== {img_path.name} === ERROR: {e}")
        continue
    elapsed = time.time() - t0

    source = j.get('_source', 'UNKNOWN')
    cats = j.get('categories', {})
    tabs = j.get('tabs', [])
    non_null = {k: v for k, v in cats.items() if v} if cats else {}
    missing = j.get('missing_categories', [])

    print(f"\n=== {img_path.name} ({elapsed:.1f}s) ===")
    print(f"  _source     : {source}")
    if cats:
        for cat, info in non_null.items():
            color = info.get('color', '?') if isinstance(info, dict) else '?'
            q0 = (info.get('searchQueries', ['?'])[0] if isinstance(info, dict) else '?')
            print(f"  {cat:12s}: color={color} | q1={q0}")
        print(f"  missing     : {missing}")
    elif tabs:
        print(f"  tabs(v3)    : {[t.get('tab') for t in tabs]}")
    else:
        print(f"  raw keys    : {list(j.keys())}")

    results.append({'file': img_path.name, 'source': source, 'cats': list(non_null.keys()), 'missing': missing})

print("\n\n=== SUMMARY ===")
v3_count = sum(1 for r in results if r['source'] == 'v3')
wg_count = sum(1 for r in results if r['source'] == 'worker_gemini')
bag_missing = sum(1 for r in results if 'bag' in r.get('missing', []))
print(f"v3 path       : {v3_count}/{len(results)}")
print(f"worker_gemini : {wg_count}/{len(results)}")
print(f"bag missing   : {bag_missing}/{len(results)}")
