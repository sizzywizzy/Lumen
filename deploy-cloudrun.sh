#!/bin/bash
# Deploy CineNode Backend to Google Cloud Run
# Usage: ./deploy-cloudrun.sh [PROJECT_ID] [REGION] [SERVICE_NAME]

set -e

PROJECT_ID=${1:-"cinenode-production"}
REGION=${2:-"us-central1"}
SERVICE_NAME=${3:-"cinenode-backend"}

echo "Deploying CineNode Backend to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"

# Build and push Docker image
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
echo "Building Docker image: $IMAGE_NAME"
docker build -t $IMAGE_NAME .
docker push $IMAGE_NAME

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 8000 \
  --cpu 1 \
  --memory 512Mi \
  --max-instances 10 \
  --min-instances 0 \
  --timeout 300s \
  --set-env-vars GEMINI_API_KEY=\$GEMINI_API_KEY \
  --set-env-vars SUPABASE_URL=\$SUPABASE_URL \
  --set-env-vars SUPABASE_KEY=\$SUPABASE_KEY \
  --set-env-vars CLOUD_SQL_CONNECTION_NAME=\$CLOUD_SQL_CONNECTION_NAME \
  --set-env-vars DB_USER=\$DB_USER \
  --set-env-vars DB_PASS=\$DB_PASS \
  --set-env-vars DB_NAME=\$DB_NAME

echo "Deployment complete!"
echo "Service URL: $(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')"
