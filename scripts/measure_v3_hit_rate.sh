#!/usr/bin/env bash
# Cloud Run v3 path 적중률 측정 — 10회 호출 후 _source 분포

ITERATIONS=${1:-10}
PAGES_URL="https://cloi.pages.dev"
TEST_IMG="${2:-fashion-search/eval/queries/q010.jpg}"

if [[ ! -f "$TEST_IMG" ]]; then
    echo "ERROR: test image not found: $TEST_IMG"
    exit 1
fi

v3_count=0
worker_count=0
none_count=0

echo "=== v3 hit rate measurement (n=$ITERATIONS) ==="
echo "image: $TEST_IMG"
echo ""

for i in $(seq 1 $ITERATIONS); do
    B64=$(base64 -w 0 < "$TEST_IMG")
    SRC=$(curl -s -X POST "$PAGES_URL/api/analyze" \
        -H "Content-Type: application/json" \
        -d "{\"imageBase64\":\"$B64\",\"mimeType\":\"image/jpeg\"}" \
        --max-time 120 \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('_source','NONE'))" 2>/dev/null || echo "ERROR")
    case "$SRC" in
        v3) v3_count=$((v3_count+1));;
        worker_gemini) worker_count=$((worker_count+1));;
        *) none_count=$((none_count+1));;
    esac
    echo "Call $i: $SRC"
done

echo ""
echo "=== Summary (n=$ITERATIONS) ==="
echo "v3:            $v3_count"
echo "worker_gemini: $worker_count"
echo "none/error:    $none_count"

HIT_RATE=$(python3 -c "print(f'{$v3_count/$ITERATIONS*100:.1f}%')")
echo "v3 hit rate:   $HIT_RATE"

if [[ $v3_count -ge $((ITERATIONS * 30 / 100)) ]]; then
    echo "PASS: v3 hit rate >= 30%"
    exit 0
else
    echo "WARN: v3 hit rate < 30% (target: 30%+)"
    exit 0
fi
