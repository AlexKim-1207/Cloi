#!/usr/bin/env bash
set -e
PROJECT_ID=${GCP_PROJECT_ID:-cloi-fashion-search}
REGION="asia-northeast3"
SERVICE_NAME="fashion-search"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=== Cloud Run 배포: ${SERVICE_NAME} (${REGION}) ==="

gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" \
  fashion-search/

gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=3 \
  --port=8080 \
  --set-env-vars="EMBEDDER_NAME=fashion_clip,KMP_DUPLICATE_LIB_OK=TRUE" \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest"

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")
echo "=== 배포 완료: ${URL} ==="
echo ""
echo "다음 단계:"
echo "  1. server/wrangler.toml FASHION_SEARCH_URL = \"${URL}\" 로 교체"
echo "  2. cd server && wrangler deploy"
