#!/bin/sh
set -e

echo "[entrypoint] Starting Python RAG server on port 8321..."
/app/python/.venv/bin/python /app/python/src/server.py &
PYTHON_PID=$!

# Wait for Python server to be ready
for i in $(seq 1 60); do
  if curl -sf http://localhost:8321/health >/dev/null 2>&1; then
    echo "[entrypoint] Python RAG server ready"
    break
  fi
  if ! kill -0 $PYTHON_PID 2>/dev/null; then
    echo "[entrypoint] Python RAG server crashed" >&2
    exit 1
  fi
  sleep 1
done

echo "[entrypoint] Starting Node.js backend..."
exec node dist/index.js
