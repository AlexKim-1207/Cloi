#!/usr/bin/env bash
set -e
PROJECT_ID=${GCP_PROJECT_ID:-cloi-fashion-search}
REGION="asia-northeast3"
SERVICE_NAME="fashion-search"

echo "=== Cloud Run 배포: ${SERVICE_NAME} (${REGION}) ==="

# 소스에서 직접 빌드 + 배포 (Cloud Build 자동 처리)
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --source="fashion-search/" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=3 \
  --port=8080 \
  --set-env-vars="EMBEDDER_NAME=fashion_clip,KMP_DUPLICATE_LIB_OK=TRUE,GOOGLE_API_KEY=${GOOGLE_API_KEY},ADMIN_TOKEN=${ADMIN_TOKEN},DEBUG=false,NAVER_CLIENT_ID=${NAVER_CLIENT_ID:-},NAVER_CLIENT_SECRET=${NAVER_CLIENT_SECRET:-}"

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")
echo "=== 배포 완료: ${URL} ==="
echo ""
echo "다음 단계:"
echo "  1. server/wrangler.toml FASHION_SEARCH_URL = \"${URL}\" 로 교체"
echo "  2. cd server && wrangler deploy"
echo ""
