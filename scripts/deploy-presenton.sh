#!/usr/bin/env bash
# Deploy Presenton as a Cloud Run service (one-time setup).
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - Secret 'gemini-api-key' exists in Secret Manager
#
# Usage:
#   bash scripts/deploy-presenton.sh

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-pe-dd-demo-03312257}"
REGION="us-central1"
SERVICE_NAME="pe-dd-presenton"
# Cloud Run can't pull from ghcr.io directly — use Artifact Registry remote repo mirror.
# Created via: gcloud artifacts repositories create ghcr-mirror --mode=remote-repository --remote-docker-repo=https://ghcr.io ...
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/ghcr-mirror/presenton/presenton:latest"

echo "==> Deploying Presenton to Cloud Run ($SERVICE_NAME in $REGION)..."

gcloud run deploy "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --port 80 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 5 \
  --min-instances 0 \
  --max-instances 3 \
  --no-cpu-throttling \
  --set-env-vars "LLM=google,GOOGLE_MODEL=models/gemini-2.5-flash,IMAGE_PROVIDER=gemini_flash,DISABLE_IMAGE_GENERATION=true,CAN_CHANGE_KEYS=false" \
  --set-secrets "GOOGLE_API_KEY=gemini-api-key:latest" \
  --allow-unauthenticated

# Print the service URL
PRESENTON_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" --region "$REGION" \
  --format "value(status.url)")

echo ""
echo "==> Presenton deployed at: $PRESENTON_URL"
echo ""
echo "Set this in your backend's Cloud Run environment:"
echo "  PRESENTON_URL=$PRESENTON_URL"
echo ""
echo "Or update .github/workflows/backend-ci-cd.yml with:"
echo "  PRESENTON_URL=$PRESENTON_URL"
