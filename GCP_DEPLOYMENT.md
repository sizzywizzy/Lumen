# Google Cloud Deployment Guide for CineNode

This guide covers deploying CineNode to Google Cloud Platform using your $300 credit budget.

## Overview

CineNode can be deployed to GCP with the following architecture:

- **Cloud Run**: Serverless deployment for backend (FastAPI) and frontend (React)
- **Supabase**: shared persistence for state, accounts and simulations
- **Cloud Build**: Automated CI/CD pipeline
- **Cloud Storage**: Media file storage (optional, future)

## Prerequisites

1. **Google Cloud Project** with $300 credits
2. **gcloud CLI** installed and authenticated
3. **Docker** installed locally for testing
4. **Environment variables** for API keys and database credentials

## Quick Start

### 1. Set up Google Cloud Project

```bash
# Set your project ID
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### 2. Configure Environment Variables

Add these to your `.env` file or Cloud Build secrets:

```bash
GEMINI_API_KEY=your_gemini_key   # all agent reasoning
SUPABASE_URL=your_supabase_url   # shared persistence (required on Cloud Run)
SUPABASE_KEY=your_supabase_key
TAVILY_API_KEY=                  # optional: cultural-research grounding
```

### 3. Deploy with Cloud Build

```bash
# Set up Cloud Build triggers
gcloud builds submit --config cloudbuild.yaml .

# Or deploy manually
./deploy-cloudrun.sh $PROJECT_ID us-central1 cinenode-backend
./deploy-frontend.sh $PROJECT_ID us-central1 cinenode-frontend
```

## Manual Deployment

### Backend Deployment

```bash
# Build and deploy backend
./deploy-cloudrun.sh your-project-id us-central1 cinenode-backend
```

### Frontend Deployment

```bash
# Build and deploy frontend
./deploy-frontend.sh your-project-id us-central1 cinenode-frontend
```

## Database Migration

The system supports two persistence backends:

1. **Supabase** — used when `SUPABASE_URL` + `SUPABASE_KEY` are set and the
   `supabase` package is installed. Apply `backend/schema_auth.sql` first.
2. **Local JSON files** under `backend/.state/` — the development fallback.

Override the choice with `CINENODE_STATE_BACKEND=local|supabase|auto` (default
`auto`).

> **Cloud Run and Replit have ephemeral filesystems.** Any deployment must run
> on Supabase; on local JSON, accounts and simulation history are lost on every
> redeploy and are not shared between instances.

## Cost Optimization

Your $300 credit budget is optimized with these settings:

- **Cloud Run**: Auto-scales to 0 when not in use
- **Backend**: 1 CPU, 512Mi RAM, max 10 instances
- **Frontend**: 0.5 CPU, 256Mi RAM, max 10 instances
- **Persistence**: Supabase free tier (no Cloud SQL instance required)

**Estimated monthly cost**: $100-125 (without AI services)

## Cloud Build Setup

### Automatic Triggers

1. Go to Cloud Build → Triggers in GCP Console
2. Create a new trigger linked to your repository
3. Configure the substitutions for secrets:
   - `_GEMINI_API_KEY`
   - `_SUPABASE_URL` 
   - `_SUPABASE_KEY`
   - `_TAVILY_API_KEY`

### Manual Build

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_GEMINI_API_KEY=$GEMINI_API_KEY,_SUPABASE_URL=$SUPABASE_URL
```

## Verification

### Check Service Status

```bash
# List Cloud Run services
gcloud run services list

# Get service URLs
gcloud run services describe cinenode-backend --region=us-central1 --format='value(status.url)'
gcloud run services describe cinenode-frontend --region=us-central1 --format='value(status.url)'
```

### Health Checks

```bash
# Backend health check
curl https://your-backend-url.a.run.app/health

# Frontend access
curl https://your-frontend-url.a.run.app
```

## Troubleshooting

### Build Failures

- Check Docker build logs: `gcloud builds log [BUILD_ID]`
- Verify all required APIs are enabled
- Ensure environment variables are properly set

### Deployment Issues

- Check Cloud Run logs: `gcloud run services logs cinenode-backend --region=us-central1`
- Verify resource limits are within your budget
- Check database connectivity

### Database Connection Issues

- Verify `SUPABASE_URL` and `SUPABASE_KEY` are set on the service
- Confirm `backend/schema_auth.sql` has been applied to the project
- Check the startup log: the app prints a warning and falls back to local JSON
  if the `supabase` package is missing
- Force a backend explicitly with `CINENODE_STATE_BACKEND=supabase` to fail
  loudly instead of silently using ephemeral local files

## Development on Replit

While production runs on GCP, you can continue development on Replit:

1. **Keep existing `.env`** with your API keys
2. **Use mock data** for development without GCP
3. **Deploy to GCP** when ready for production
4. **Use CI/CD** for automated deployments from your repository

## Scaling Considerations

For higher traffic or production workloads:

1. **Increase Cloud Run instances**: Modify `--max-instances` in deployment scripts
2. **Upgrade Supabase plan**: Move off the free tier for higher connection limits
3. **Add Cloud CDN**: For static asset delivery
4. **Load balancing**: Use Cloud Load Balancing for multiple regions

## Security Best Practices

1. **Use Secret Manager**: Store sensitive keys in GCP Secret Manager
2. **IAM roles**: Grant minimum required permissions
3. **VPC connectors**: Use private connections for managed databases
4. **Network policies**: Restrict access to Cloud Run services

## Monitoring and Logging

```bash
# View logs
gcloud logging read "resource.type=cloud_run"

# Set up monitoring
gcloud monitoring dashboards create
```

## Rollback

If you need to rollback to a previous version:

```bash
# List revisions
gcloud run revisions list --service=cinenode-backend --region=us-central1

# Rollback to specific revision
gcloud run services update-traffic cinenode-backend \
  --region=us-central1 \
  --to-revisions=[REVISION_NAME]=100
```

## Support

For issues specific to:
- **CineNode**: Check AGENT.md and existing documentation
- **Google Cloud**: Use GCP Console and Cloud Support
- **Deployment**: Review Cloud Build logs and Cloud Run logs
