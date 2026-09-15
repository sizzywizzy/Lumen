# Dockerfile for the Lumen backend (FastAPI). Render builds it from render.yaml;
# the same image runs on any container host (Cloud Run, Railway, Fly.io).
# Multi-stage build for optimization

FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY backend/ .
# SKILL.md files live beside backend/ in the repo; keep that layout in the image
COPY skills/ /skills/

# Hosts inject the port to listen on as $PORT (Render sets 10000); 8000 is the
# default everywhere else.
ENV PORT=8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/api/health' % os.environ.get('PORT', '8000'))"

# Run the application. `exec` hands PID 1 to uvicorn so it receives the host's
# SIGTERM and shuts down cleanly on redeploy.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
