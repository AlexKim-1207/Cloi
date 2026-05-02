"""
SESSION 13 Live QA — Pattern / Length / Ambiguity Signal 검증
Usage: python fashion-search/scripts/live_qa_s13.py [--url URL] [--img-dir DIR]
"""
import argparse, base64, json, sys
from pathlib import Path
import urllib.request, urllib.error

URL = 'https://cloi.pages.dev/api/analyze'
EVAL_DIR = Path(__file__).parent.parent / 'eval' / 'queries'

CASES = [
    # (image_glob_pattern, label, expected_checks)
    # expected_checks: {category.field: value_substring}
    ('q030.jpg', '그라데이션 롱 드레스/상의', {
        'top_inner.pattern': ['그라데이션', '기타'],
        'top_inner.length': ['롱'],
    }),
    ('q045.jpg', '단색 반팔 + 청바지', {
        'top_inner.pattern': ['단색'],
        'top_inner.length': ['숏', '반팔'],
        'bottom.length': ['풀렝스', '롱'],
    }),
    ('q010.jpg', '워커부츠 단색', {
        'shoes.pattern': ['단색'],
    }),
]


def call_analyze(img_path: Path, url: str) -> dict:
    with open(img_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = json.dumps({'imageBase64': b64, 'mimeType': 'image/jpeg'}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            'Content-Type': 'application/json',
            'Origin': 'https://cloi.pages.dev',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        return {'error': f'HTTP {e.code}: {body[:200]}'}
    except Exception as ex:
        return {'error': str(ex)}


def check_result(result: dict, checks: dict) -> list[tuple[str, bool, str]]:
    """Returns list of (check_key, passed, actual_value)."""
    outcomes = []
    cats = result.get('categories', {})
    for check_key, expected_values in checks.items():
        cat_name, field = check_key.split('.', 1)
        cat = cats.get(cat_name)
        if not cat:
            outcomes.append((check_key, False, f'category {cat_name} missing'))
            continue
        actual = cat.get(field, None)
        actual_str = str(actual) if actual is not None else 'null'
        passed = any(ev.lower() in actual_str.lower() for ev in expected_values)
        outcomes.append((check_key, passed, actual_str))
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=URL)
    parser.add_argument('--img-dir', default=str(EVAL_DIR))
    args = parser.parse_args()

    img_dir = Path(args.img_dir)
    total_checks = 0
    passed_checks = 0

    print(f'=== SESSION 13 Live QA ===')
    print(f'URL: {args.url}')
    print()

    for img_name, label, checks in CASES:
        img_path = img_dir / img_name
        if not img_path.exists():
            print(f'[SKIP] {img_name} not found')
            continue

        print(f'--- {img_name}: {label} ---')
        result = call_analyze(img_path, args.url)

        if 'error' in result or result.get('code') == 'IMAGE_QUALITY':
            print(f'  ERROR: {result.get("error") or result.get("message")}')
            print()
            continue

        src = result.get('_source', '?')
        print(f'  _source: {src}')

        cats = result.get('categories', {})
        for k, v in cats.items():
            if v:
                pat = v.get('pattern', '-')
                lng = v.get('length', '-')
                alt = v.get('alternative_subtypes', [])
                sub = v.get('subtype', '?')
                print(f'  {k}: pattern={pat} length={lng} alt={alt} subtype={sub}')

        outcomes = check_result(result, checks)
        for key, passed, actual in outcomes:
            total_checks += 1
            if passed:
                passed_checks += 1
                print(f'  [PASS] {key}: "{actual}"')
            else:
                print(f'  [FAIL] {key}: got "{actual}" (expected one of {checks[key]})')
        print()

    score = passed_checks / total_checks * 100 if total_checks else 0
    print(f'=== RESULT: {passed_checks}/{total_checks} checks passed ({score:.0f}%) ===')
    sys.exit(0 if score >= 70 else 1)


if __name__ == '__main__':
    main()
