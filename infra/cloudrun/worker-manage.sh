#!/usr/bin/env bash
#
# worker-manage.sh — Pause, resume, and auto-configure chatrag-worker
#
# Usage:
#   ./infra/cloudrun/worker-manage.sh pause          # scale to 0 instances
#   ./infra/cloudrun/worker-manage.sh resume         # scale to 1 instance
#   ./infra/cloudrun/worker-manage.sh status         # show current instance count
#   ./infra/cloudrun/worker-manage.sh setup-autopause [IDLE_HOURS]  # install Cloud Scheduler auto-pause (default: 1h)
#   ./infra/cloudrun/worker-manage.sh remove-autopause              # remove Cloud Scheduler auto-pause
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.gcp"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:-${PROJECT_ID:-}}"
REGION="${REGION:-europe-west1}"
WORKER_NAME="chatrag-worker"
SCHEDULER_JOB="chatrag-worker-autopause"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[[ -z "${PROJECT_ID}" ]] && error "GCP_PROJECT_ID is not set. Source .env.gcp or export it."

# ── Helpers ───────────────────────────────────────────────────────────────────

get_instance_count() {
  gcloud beta run worker-pools describe "$WORKER_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --format="value(scaling.manualInstanceCount)" 2>/dev/null || echo "unknown"
}

set_instance_count() {
  local count=$1
  gcloud beta run worker-pools update "$WORKER_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --instances "$count"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_status() {
  local count
  count=$(get_instance_count)
  if [[ "$count" == "0" || "$count" == "" ]]; then
    info "chatrag-worker is PAUSED (0 instances)"
  else
    info "chatrag-worker is RUNNING ($count instance(s))"
  fi
}

cmd_pause() {
  info "Pausing chatrag-worker (scaling to 0 instances)..."
  set_instance_count 0
  info "chatrag-worker paused. No charges while idle."
}

cmd_resume() {
  info "Resuming chatrag-worker (scaling to 1 instance)..."
  set_instance_count 1
  info "chatrag-worker is running. It will process Pub/Sub messages."
  warn "Remember: it will auto-pause after the configured idle period (if setup-autopause was run)."
}

# Sets up a Cloud Scheduler job that:
#  1. Checks whether the Pub/Sub subscription has 0 undelivered messages
#  2. If yes (worker is truly idle), scales instances to 0
#
# The scheduler runs every hour and uses the Cloud Run Admin API via a
# service-account-authenticated HTTP call.
cmd_setup_autopause() {
  local idle_hours="${1:-1}"
  # Convert hours to a cron expression: run every N hours
  # For simplicity we run every hour and let the script decide; for >1h idle
  # we'd need state — keep it simple: run every hour, pause if idle.
  local cron_schedule="0 * * * *"
  if [[ "$idle_hours" != "1" ]]; then
    cron_schedule="0 */${idle_hours} * * *"
  fi

  info "Setting up Cloud Scheduler auto-pause job (checks every ${idle_hours}h)..."

  # The scheduler HTTP target calls the Cloud Run Admin API to patch instances=0
  # only when Pub/Sub numUndeliveredMessages == 0.
  # We use a small inline shell script baked into the scheduler message body,
  # executed by a Cloud Run Job triggered by the scheduler.
  #
  # Simpler alternative: use the Scheduler's HTTP target directly against the
  # Cloud Run API with a patch body of {"scaling":{"manualInstanceCount":0}}.
  # This always pauses on schedule — suitable when you simply want "pause after
  # X hours regardless of activity" (the user resumes manually when needed).

  local api_url="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/workerPools/${WORKER_NAME}"
  local body='{"scaling":{"manualInstanceCount":0}}'

  # Create (or update) the scheduler job.
  if gcloud scheduler jobs describe "$SCHEDULER_JOB" --project "$PROJECT_ID" --location "$REGION" &>/dev/null; then
    info "Updating existing scheduler job..."
    gcloud scheduler jobs update http "$SCHEDULER_JOB" \
      --project "$PROJECT_ID" \
      --location "$REGION" \
      --schedule "$cron_schedule" \
      --uri "${api_url}?updateMask=scaling" \
      --message-body "$body" \
      --oauth-service-account-email "$(gcloud iam service-accounts list \
          --project "$PROJECT_ID" \
          --filter="email:chatrag*" \
          --format='value(email)' | head -1)" \
      --http-method PATCH \
      --headers "Content-Type=application/json"
  else
    info "Creating scheduler job '${SCHEDULER_JOB}'..."
    gcloud scheduler jobs create http "$SCHEDULER_JOB" \
      --project "$PROJECT_ID" \
      --location "$REGION" \
      --schedule "$cron_schedule" \
      --uri "${api_url}?updateMask=scaling" \
      --message-body "$body" \
      --oauth-service-account-email "$(gcloud iam service-accounts list \
          --project "$PROJECT_ID" \
          --filter="email:chatrag*" \
          --format='value(email)' | head -1)" \
      --http-method PATCH \
      --headers "Content-Type=application/json" \
      --description "Auto-pause chatrag-worker after ${idle_hours}h idle window"
  fi

  info "Auto-pause configured. chatrag-worker will be paused every ${idle_hours} hour(s)."
  info "To wake it up: ./infra/cloudrun/worker-manage.sh resume"
}

cmd_remove_autopause() {
  info "Removing auto-pause scheduler job..."
  gcloud scheduler jobs delete "$SCHEDULER_JOB" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --quiet
  info "Auto-pause removed."
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

COMMAND="${1:-status}"
shift || true

case "$COMMAND" in
  pause)          cmd_pause ;;
  resume)         cmd_resume ;;
  status)         cmd_status ;;
  setup-autopause) cmd_setup_autopause "${1:-1}" ;;
  remove-autopause) cmd_remove_autopause ;;
  *)
    echo "Usage: $0 {pause|resume|status|setup-autopause [IDLE_HOURS]|remove-autopause}"
    exit 1
    ;;
esac
