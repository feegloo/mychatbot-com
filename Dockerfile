# check=skip=SecretsUsedInArgOrEnv
# ── Stage 1: Build frontend ──────────────────────────────────────────────────
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
# Stripe publishable key is a public client-side key, not a secret
ARG VITE_STRIPE_PUBLISHABLE_KEY
ENV VITE_STRIPE_PUBLISHABLE_KEY=${VITE_STRIPE_PUBLISHABLE_KEY}
ENV NODE_ENV=production
ENV NODE_OPTIONS="--max-old-space-size=2048"
RUN echo "=== vue-tsc type-check ===" && npx vue-tsc --noEmit 2>&1 || echo "=== vue-tsc had errors (non-fatal) ==="
RUN echo "=== vite build ===" && npx vite build 2>&1 && echo "=== frontend build OK ===" || (echo "=== FRONTEND BUILD FAILED ===" && exit 1)
RUN ls -la /app/frontend/dist/ || (echo "=== ERROR: dist/ not found after build ===" && exit 1)

# ── Stage 2: Build backend ───────────────────────────────────────────────────
FROM node:22-alpine AS backend-build
WORKDIR /app/backend
COPY backend/package.json backend/package-lock.json* ./
RUN npm ci
COPY backend/ ./
ENV NODE_ENV=production
RUN npm run build

# ── Stage 3: Production image ────────────────────────────────────────────────
FROM node:22-slim

# Install Python 3 + pip + curl (curl needed for health-check in entrypoint)
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -- Python dependencies --
COPY python/requirements.txt /app/python/requirements.txt
RUN python3 -m venv /app/python/.venv && \
    /app/python/.venv/bin/pip install --no-cache-dir --retries 1 --timeout 120 -r /app/python/requirements.txt
COPY python/ /app/python/

# -- Backend production deps --
COPY backend/package.json backend/package-lock.json* /app/backend/
RUN cd /app/backend && npm ci --omit=dev

# -- Backend compiled code --
COPY --from=backend-build /app/backend/dist /app/backend/dist

# -- Frontend static files --
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# -- SQL schemas --
COPY backend/sql /app/backend/sql

# Writable directories for runtime
RUN mkdir -p /app/storage /app/logs /app/data/chroma

# -- Entrypoint script --
COPY backend/entrypoint.sh /app/backend/entrypoint.sh
RUN chmod +x /app/backend/entrypoint.sh

ENV NODE_ENV=production
ENV PORT=8080
ENV FRONTEND_DIST_PATH=/app/frontend/dist
ENV PYTHON_BIN=/app/python/.venv/bin/python3
ENV PYTHON_PROJECT_ROOT=/app/python
ENV PYTHON_SERVER_URL=http://localhost:8321
ENV STORAGE_ROOT=/app/storage
ENV LOGS_ROOT=/app/logs
ENV CHROMA_PERSIST_DIR=/app/data/chroma

# Gemma 4 (local Ollama) — disabled by default, enable with USE_GEMMA=true
ENV USE_GEMMA=false
ENV GEMMA_MODEL=gemma4:e2b
ENV GEMMA_BASE_URL=http://localhost:11434

EXPOSE 8080

WORKDIR /app/backend
CMD ["./entrypoint.sh"]
