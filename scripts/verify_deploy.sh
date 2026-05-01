#!/usr/bin/env bash
# verify_deploy.sh — Pages + Cloud Run 배포 검증 (필수)
#
# 사용:
#   bash scripts/verify_deploy.sh [TEST_IMAGE_PATH]
#
# Exit codes:
#   0 = 모든 검증 통과
#   1 = wrangler 인증 실패
#   2 = Pages 응답 누락 필드 (_source 등)
#   3 = Cloud Run /health 실패
#   5 = 응답 schema 불일치 (8키 schema 미적용)
#
# CLAUDE.md 규칙:
#   "wrangler pages deploy 후 반드시 verify_deploy.sh 실행. 실패 시 SESSION_STATUS.md 업데이트 금지."

set -uo pipefail

# ─── 설정 ─────────────────────────────────────────────────
PAGES_URL="${PAGES_URL:-https://cloi.pages.dev}"
WORKER_URL="${WORKER_URL:-https://cloi-api.kyoung361207.workers.dev}"
CLOUD_RUN_URL="${CLOUD_RUN_URL:-https://fashion-search-dibvogjuma-du.a.run.app}"
TEST_IMAGE="${1:-fashion-search/eval/queries/q001.jpg}"

GREEN=$'\033[0;32m'
RED=$'\033[0;31m'
YELLOW=$'\033[1;33m'
NC=$'\033[0m'

ok()   { echo "${GREEN}OK${NC} $*"; }
fail() { echo "${RED}FAIL${NC} $*"; }
warn() { echo "${YELLOW}WARN${NC} $*"; }

echo "============================================================"
echo "  Cloi Deploy Verification"
echo "  Date: $(date +'%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo "Pages URL (real prod): $PAGES_URL"
echo "Worker URL (legacy)  : $WORKER_URL"
echo "Cloud Run URL        : $CLOUD_RUN_URL"
echo "Test image           : $TEST_IMAGE"
echo ""

# ─── Step 1. 테스트 이미지 ───────────────────────────────
echo "[1/4] Test image base64..."
if [ ! -f "$TEST_IMAGE" ]; then
    fail "Test image not found: $TEST_IMAGE"
    exit 2
fi
B64=$(base64 -w 0 < "$TEST_IMAGE" 2>/dev/null || base64 < "$TEST_IMAGE" | tr -d '\n')
ok "image base64 (${#B64} chars)"

# ─── Step 2. Pages /api/analyze ──────────────────────────
echo ""
echo "[2/4] POST $PAGES_URL/api/analyze ..."
PAYLOAD=$(printf '{"imageBase64":"%s","mimeType":"image/jpeg"}' "$B64")
RESP_TMP=$(mktemp 2>/dev/null || echo "/tmp/cloi_resp_$$.json")
# curl 직접 파일 저장 (bash 변수 거치면 UTF-8 깨짐)
curl -s -X POST "$PAGES_URL/api/analyze" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    --max-time 60 -o "$RESP_TMP" 2>/dev/null || echo '{"error":"curl failed"}' > "$RESP_TMP"
RESPONSE=$(cat "$RESP_TMP" 2>/dev/null || echo '{}')

# Single python parse — extract all fields at once
PARSED=$(python3 - "$RESP_TMP" << 'PYEOF'
import json, sys
try:
    with open(sys.argv[1], encoding='utf-8') as f:
        d = json.load(f)
    src = d.get('_source', 'MISSING')
    cat_keys = ','.join(sorted((d.get('categories') or {}).keys()))
    has_8key = any(k in (d.get('categories') or {}) for k in ['top_outer','top_inner','dress'])
    has_gender = 'gender' in d
    has_price = 'price_tier' in d
    has_missing = 'missing_categories' in d
    print(f"SOURCE={src}")
    print(f"CAT_KEYS={cat_keys}")
    print(f"HAS_8KEY={'YES' if has_8key else 'NO'}")
    print(f"HAS_GENDER={'YES' if has_gender else 'NO'}")
    print(f"HAS_PRICE={'YES' if has_price else 'NO'}")
    print(f"HAS_MISSING={'YES' if has_missing else 'NO'}")
except Exception as e:
    print(f"SOURCE=PARSE_ERROR")
    print(f"CAT_KEYS=")
    print(f"HAS_8KEY=NO")
    print(f"HAS_GENDER=NO")
    print(f"HAS_PRICE=NO")
    print(f"HAS_MISSING=NO")
PYEOF
)

eval "$PARSED"
echo "Response sample (first 300 chars): $(echo "$RESPONSE" | head -c 300)"
echo ""

# ─── Step 3. Schema 검증 ─────────────────────────────────
echo "[3/4] Schema check..."

if [ "$SOURCE" = "MISSING" ] || [ "$SOURCE" = "PARSE_ERROR" ]; then
    fail "_source missing → SESSION 11 worker code NOT in production"
    fail "Run: npm run build && npx wrangler pages deploy dist --project-name=cloi"
    rm -f "$RESP_TMP"
    exit 2
fi
ok "_source = '$SOURCE'"

if [ "$HAS_8KEY" = "YES" ]; then
    ok "8-key schema applied (categories: $CAT_KEYS)"
else
    fail "OLD 6-key schema — SESSION 11 FASHION_PROMPT NOT deployed (categories: $CAT_KEYS)"
    rm -f "$RESP_TMP"
    exit 5
fi

if [ "$HAS_GENDER" = "YES" ] && [ "$HAS_PRICE" = "YES" ]; then
    ok "SESSION 12 outfit_meta applied (gender + price_tier present)"
else
    warn "SESSION 12 outfit_meta missing (gender=$HAS_GENDER price_tier=$HAS_PRICE)"
    warn "→ SESSION 12 Track B not yet deployed (OK if SESSION 11 only)"
fi

if [ "$HAS_MISSING" = "YES" ]; then
    ok "missing_categories field present"
else
    warn "missing_categories field absent"
fi

# ─── Step 4. Cloud Run /health ───────────────────────────
echo ""
echo "[4/4] Cloud Run /health ..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$CLOUD_RUN_URL/health" --max-time 10 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
    ok "Cloud Run /health 200"
else
    fail "Cloud Run /health $HEALTH"
    rm -f "$RESP_TMP"
    exit 3
fi

# ─── 종합 ─────────────────────────────────────────────────
rm -f "$RESP_TMP"
echo ""
echo "============================================================"
ok "All checks passed"
echo "  _source       : $SOURCE"
echo "  schema 8-key  : $HAS_8KEY"
echo "  SESSION 12 meta: gender=$HAS_GENDER price=$HAS_PRICE"
echo "============================================================"
exit 0
