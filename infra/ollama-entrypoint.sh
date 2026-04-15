#!/bin/sh
# Custom entrypoint: start Ollama, auto-pull required model, then keep serving.
set -e

MODEL="${OLLAMA_MODEL:-gemma4:e2b}"

echo "[ollama-entrypoint] Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# Wait for the server to be ready
for i in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Pull the model if not already present
if ! ollama list | grep -q "^${MODEL}"; then
  echo "[ollama-entrypoint] Pulling model: ${MODEL} ..."
  ollama pull "$MODEL"
  echo "[ollama-entrypoint] Model ${MODEL} ready."
else
  echo "[ollama-entrypoint] Model ${MODEL} already present."
fi

# Keep the server running
wait $SERVER_PID
