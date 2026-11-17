# ==============================================================================
# Multi-Stage Dockerfile for KrishiSetu (Single-URL Deployment)
# Stage 1: Build Frontend (Vite + React + TypeScript + Tailwind)
# Stage 2: Python Backend (FastAPI + Unified Static Serving)
# ==============================================================================

# ----------------- Stage 1: Node.js Frontend Builder -----------------
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy package manifests and install dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source files and compile static production build
COPY frontend/ ./
RUN npm run build

# ----------------- Stage 2: Python Production Runtime -----------------
FROM python:3.11-slim AS runtime
WORKDIR /app

# Prevent Python from writing .pyc files & enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python backend dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend application source
COPY backend/ ./backend/

# Copy compiled frontend production artifacts from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Default port configuration
EXPOSE 8000

# Start Uvicorn bound to 0.0.0.0:${PORT:-8000}
CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
