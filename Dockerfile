# check=skip=SecretsUsedInArgOrEnv
# ── Stage 1b: Build ui (new SPA, served under /v2/) ──────────────────────────
FROM node:22-alpine AS ui-build
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json* ./
RUN set -eux; \
        npm config set fetch-retries 5; \
        npm config set fetch-retry-mintimeout 20000; \
        npm config set fetch-retry-maxtimeout 120000; \
        for attempt in 1 2 3; do \
            npm ci && break; \
            if [ "$attempt" -eq 3 ]; then \
                exit 1; \
            fi; \
            echo "npm ci failed (attempt $attempt), retrying in 10s..."; \
            sleep 10; \
        done
COPY ui/ ./
# ui imports HomeHero from frontend via alias ../../frontend/src/...
COPY frontend/src /app/frontend/src
ENV NODE_ENV=production
RUN echo "=== ui vite build ===" && npx vite build 2>&1 && echo "=== ui build OK ===" || (echo "=== UI BUILD FAILED ===" && exit 1)
RUN ls -la /app/ui/dist/ || (echo "=== ERROR: ui/dist/ not found after build ===" && exit 1)

# ── Stage 2: Build backend ───────────────────────────────────────────────────
FROM node:22-alpine AS backend-build
WORKDIR /app/backend
COPY backend/package.json backend/package-lock.json* ./
RUN set -eux; \
        npm config set fetch-retries 5; \
        npm config set fetch-retry-mintimeout 20000; \
        npm config set fetch-retry-maxtimeout 120000; \
        for attempt in 1 2 3; do \
            npm ci && break; \
            if [ "$attempt" -eq 3 ]; then \
                exit 1; \
            fi; \
            echo "npm ci failed (attempt $attempt), retrying in 10s..."; \
            sleep 10; \
        done
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
RUN set -eux; \
        cd /app/backend; \
        npm config set fetch-retries 5; \
        npm config set fetch-retry-mintimeout 20000; \
        npm config set fetch-retry-maxtimeout 120000; \
        for attempt in 1 2 3; do \
            npm ci --omit=dev && break; \
            if [ "$attempt" -eq 3 ]; then \
                exit 1; \
            fi; \
            echo "npm ci --omit=dev failed (attempt $attempt), retrying in 10s..."; \
            sleep 10; \
        done

# -- Backend compiled code --
COPY --from=backend-build /app/backend/dist /app/backend/dist

# -- New ui SPA (served under /v2/) --
COPY --from=ui-build /app/ui/dist /app/ui/dist

# -- SQL schemas --
COPY backend/sql /app/backend/sql

# Writable directories for runtime
RUN mkdir -p /app/storage /app/logs /app/data/chroma

# -- Entrypoint script --
COPY backend/entrypoint.sh /app/backend/entrypoint.sh
RUN chmod +x /app/backend/entrypoint.sh

ENV NODE_ENV=production
ENV PORT=8080
ENV UI_DIST_PATH=/app/ui/dist
ENV PYTHON_BIN=/app/python/.venv/bin/python3
ENV PYTHON_PROJECT_ROOT=/app/python
ENV PYTHON_SERVER_URL=http://localhost:8321
ENV STORAGE_ROOT=/app/storage
ENV LOGS_ROOT=/app/logs
ENV CHROMA_PERSIST_DIR=/app/data/chroma
ENV ANONYMIZED_TELEMETRY=False

EXPOSE 8080

WORKDIR /app/backend
CMD ["./entrypoint.sh"]
