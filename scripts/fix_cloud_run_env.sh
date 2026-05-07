#!/usr/bin/env bash
# fix_cloud_run_env.sh
# fashion-search/.env 파일을 읽어 Cloud Run service의 환경변수 일괄 update.
#
# 사용:
#   bash scripts/fix_cloud_run_env.sh
#
# 동작:
#   1. fashion-search/.env 읽기
#   2. KEY=VALUE 형식 라인 추출
#   3. gcloud run services update --set-env-vars 호출
#   4. 새 revision 자동 생성 + 환경변수 적용 (1~2분)

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/fashion-search/.env"
SERVICE="fashion-search"
REGION="asia-northeast3"

echo "============================================================"
echo "  Cloud Run Env Fix"
echo "  Service : $SERVICE"
echo "  Region  : $REGION"
echo "  EnvFile : $ENV_FILE"
echo "============================================================"

# 1. .env 존재 확인
if [ ! -f "$ENV_FILE" ]; then
    echo "[FAIL] .env not found: $ENV_FILE"
    exit 1
fi

# 2. .env 파싱 (KEY=VALUE 라인만, 주석/빈줄 제외)
declare -A ENV_KV
while IFS='=' read -r key value; do
    # 주석/빈줄 skip
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$key" ]] && continue
    # KEY 형식 확인 (대문자 + 언더스코어)
    [[ ! "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] && continue
    # value 따옴표/공백 제거
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    value="${value%$'\r'}"  # CR 제거 (Windows line ending)
    ENV_KV["$key"]="$value"
done < "$ENV_FILE"

# 3. 필수 키 체크
REQUIRED=("GOOGLE_API_KEY" "NAVER_CLIENT_ID" "NAVER_CLIENT_SECRET")
MISSING=()
for k in "${REQUIRED[@]}"; do
    if [ -z "${ENV_KV[$k]:-}" ]; then
        MISSING+=("$k")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "[FAIL] Required keys missing in .env: ${MISSING[*]}"
    exit 2
fi

# 4. gcloud용 string 생성 (KEY=VALUE,KEY=VALUE,...)
KV_ARGS=()
KEYS_LIST=()
for key in "${!ENV_KV[@]}"; do
    KV_ARGS+=("$key=${ENV_KV[$key]}")
    KEYS_LIST+=("$key")
done
ENV_STRING=$(IFS=','; echo "${KV_ARGS[*]}")

echo ""
echo "Detected ${#ENV_KV[@]} env vars:"
for k in "${KEYS_LIST[@]}"; do
    val="${ENV_KV[$k]}"
    masked="${val:0:4}***${val: -4}"
    echo "  $k = $masked"
done
echo ""

# 5. gcloud run services update 호출
echo "Updating Cloud Run service..."
gcloud run services update "$SERVICE" \
    --region="$REGION" \
    --set-env-vars="$ENV_STRING" \
    --quiet

EXIT=$?
echo ""
if [ $EXIT -eq 0 ]; then
    echo "[OK] Cloud Run env vars updated. New revision creating (1-2 min)."
    echo ""
    echo "Verify in 2 min:"
    echo "  curl https://fashion-search-dibvogjuma-du.a.run.app/health"
    echo "  bash scripts/verify_deploy.sh fashion-search/eval/queries/q010.jpg"
else
    echo "[FAIL] gcloud update failed (exit $EXIT)"
fi
exit $EXIT
