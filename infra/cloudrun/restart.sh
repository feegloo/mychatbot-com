#!/usr/bin/env bash
# Restart Cloud Run services without rebuilding/redeploying the image.
#
# Cloud Run has no native "restart" — but updating any service config forces
# a new revision that pulls the same image and spins up fresh containers.
# We use a throwaway ``RESTARTED_AT`` env var as the no-op trigger.
#
# Usage:
#   ./restart.sh              # restart both (chatrag + chatrag-worker)
#   ./restart.sh app          # only the main service
#   ./restart.sh worker       # only the worker pool
#
# Requires: gcloud, GCP_PROJECT_ID env (or pre-set default project).

set -euo pipefail

REGION="${GCP_REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-chatrag}"
WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-chatrag-worker}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

TARGET="${1:-both}"

restart_service() {
  echo "→ Restarting service '$SERVICE_NAME' in $REGION ..."
  gcloud run services update "$SERVICE_NAME" \
    --region="$REGION" \
    --update-env-vars="RESTARTED_AT=${STAMP}" \
    --quiet
  echo "✓ $SERVICE_NAME restarted (new revision, RESTARTED_AT=${STAMP})"
}

restart_worker() {
  echo "→ Restarting worker pool '$WORKER_SERVICE_NAME' in $REGION ..."
  gcloud beta run worker-pools update "$WORKER_SERVICE_NAME" \
    --region="$REGION" \
    --update-env-vars="RESTARTED_AT=${STAMP}" \
    --quiet
  echo "✓ $WORKER_SERVICE_NAME restarted (new revision, RESTARTED_AT=${STAMP})"
}

case "$TARGET" in
  app)    restart_service ;;
  worker) restart_worker ;;
  both)   restart_service; restart_worker ;;
  *)
    echo "Unknown target: $TARGET (expected: app | worker | both)" >&2
    exit 1
    ;;
esac
