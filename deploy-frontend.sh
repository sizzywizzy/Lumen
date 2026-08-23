#!/bin/bash
# Deploy CineNode Frontend to Google Cloud Run
# Usage: ./deploy-frontend.sh [PROJECT_ID] [REGION] [SERVICE_NAME]

set -e

PROJECT_ID=${1:-"cinenode-production"}
REGION=${2:-"us-central1"}
SERVICE_NAME=${3:-"cinenode-frontend"}

echo "Deploying CineNode Frontend to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"

# Build and push Docker image
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
echo "Building Docker image: $IMAGE_NAME"
cd frontend
docker build -t $IMAGE_NAME .
docker push $IMAGE_NAME
cd ..

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 80 \
  --cpu 0.5 \
  --memory 256Mi \
  --max-instances 10 \
  --min-instances 0 \
  --timeout 60s

echo "Deployment complete!"
echo "Service URL: $(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')"
