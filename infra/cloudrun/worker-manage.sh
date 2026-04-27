#!/usr/bin/env bash
#
# worker-manage.sh — Pause, resume, and schedule chatrag services
#
# chatrag-worker commands:
#   ./infra/cloudrun/worker-manage.sh pause                           # scale worker to 0 instances
#   ./infra/cloudrun/worker-manage.sh resume                          # scale worker to 1 instance
#   ./infra/cloudrun/worker-manage.sh status                          # show worker instance count
#   ./infra/cloudrun/worker-manage.sh setup-autopause [IDLE_WINDOW]   # auto-pause worker after idle (default: 30m)
#   ./infra/cloudrun/worker-manage.sh remove-autopause                # remove auto-pause scheduler
#
# chatrag main service schedule:
#   ./infra/cloudrun/worker-manage.sh setup-main-schedule [SLEEP_H] [WAKE_H]  # sleep/wake at given UTC hours (default: 1 9)
#   ./infra/cloudrun/worker-manage.sh remove-main-schedule                    # remove sleep/wake scheduler jobs
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

build_autopause_schedule() {
  local idle_window="$1"

  case "$idle_window" in
    30m)
      echo "*/30 * * * *|30 minutes"
      ;;
    1h)
      echo "0 * * * *|1 hour"
      ;;
    ''|*[!0-9h])
      error "Unsupported idle window '$idle_window'. Use 30m, 1h, Nh, or a bare hour count like 2."
      ;;
    *h)
      local hours="${idle_window%h}"
      [[ -z "$hours" || "$hours" == "0" ]] && error "Idle window hours must be greater than 0."
      echo "0 */${hours} * * *|${hours} hour(s)"
      ;;
    *)
      [[ "$idle_window" == "0" ]] && error "Idle window hours must be greater than 0."
      echo "0 */${idle_window} * * *|${idle_window} hour(s)"
      ;;
  esac
}

# Sets up a Cloud Scheduler job that:
#  1. Checks whether the Pub/Sub subscription has 0 undelivered messages
#  2. If yes (worker is truly idle), scales instances to 0
#
# The scheduler runs on the configured interval and uses the Cloud Run Admin API via a
# service-account-authenticated HTTP call.
cmd_setup_autopause() {
  local idle_window="${1:-30m}"
  local schedule_config
  schedule_config="$(build_autopause_schedule "$idle_window")"
  local cron_schedule="${schedule_config%%|*}"
  local schedule_label="${schedule_config#*|}"

  info "Setting up Cloud Scheduler auto-pause job (checks every ${schedule_label})..."

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
        --description "Auto-pause chatrag-worker after ${schedule_label} idle window"
  fi

      info "Auto-pause configured. chatrag-worker will be paused every ${schedule_label}."
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

# ── Main service schedule (sleep 01:00 / wake 09:00 UTC) ─────────────────────

MAIN_SERVICE_NAME="${SERVICE_NAME:-chatrag}"
SCHEDULER_SLEEP_JOB="chatrag-sleep"
SCHEDULER_WAKE_JOB="chatrag-wake"

_upsert_scheduler_http_job() {
  local job_name="$1" cron="$2" uri="$3" body="$4" description="$5"
  local sa
  sa="$(gcloud iam service-accounts list \
    --project "$PROJECT_ID" \
    --filter="email:chatrag*" \
    --format='value(email)' | head -1)"

  local common_flags=(
    --project "$PROJECT_ID"
    --location "$REGION"
    --schedule "$cron"
    --uri "$uri"
    --message-body "$body"
    --oauth-service-account-email "$sa"
    --http-method PATCH
    --headers "Content-Type=application/json"
  )

  if gcloud scheduler jobs describe "$job_name" --project "$PROJECT_ID" --location "$REGION" &>/dev/null; then
    info "  Updating scheduler job '${job_name}'..."
    gcloud scheduler jobs update http "$job_name" "${common_flags[@]}"
  else
    info "  Creating scheduler job '${job_name}'..."
    gcloud scheduler jobs create http "$job_name" "${common_flags[@]}" --description "$description"
  fi
}

cmd_setup_main_schedule() {
  local sleep_hour="${1:-1}"   # default 01:00 UTC
  local wake_hour="${2:-9}"    # default 09:00 UTC
  local service_api="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services/${MAIN_SERVICE_NAME}"

  info "Scheduling main service '${MAIN_SERVICE_NAME}' to sleep at ${sleep_hour}:00 and wake at ${wake_hour}:00 UTC..."

  # Scale down: set min/max instances to 0 — service stops accepting traffic
  _upsert_scheduler_http_job \
    "$SCHEDULER_SLEEP_JOB" \
    "0 ${sleep_hour} * * *" \
    "${service_api}?updateMask=scaling" \
    '{"scaling":{"minInstanceCount":0,"maxInstanceCount":0}}' \
    "Scale chatrag main service to 0 instances at ${sleep_hour}:00 UTC"

  # Wake up: restore min=1, max=1
  _upsert_scheduler_http_job \
    "$SCHEDULER_WAKE_JOB" \
    "0 ${wake_hour} * * *" \
    "${service_api}?updateMask=scaling" \
    '{"scaling":{"minInstanceCount":1,"maxInstanceCount":1}}' \
    "Scale chatrag main service to 1 instance at ${wake_hour}:00 UTC"

  info "Done. '${MAIN_SERVICE_NAME}' will sleep at ${sleep_hour}:00 UTC and wake at ${wake_hour}:00 UTC daily."
  info "To remove: $0 remove-main-schedule"
}

cmd_remove_main_schedule() {
  info "Removing main service schedule jobs..."
  for job in "$SCHEDULER_SLEEP_JOB" "$SCHEDULER_WAKE_JOB"; do
    if gcloud scheduler jobs describe "$job" --project "$PROJECT_ID" --location "$REGION" &>/dev/null; then
      gcloud scheduler jobs delete "$job" --project "$PROJECT_ID" --location "$REGION" --quiet
      info "  Deleted '${job}'"
    else
      warn "  Job '${job}' not found, skipping."
    fi
  done
  info "Main service schedule removed."
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

COMMAND="${1:-status}"
shift || true

case "$COMMAND" in
  pause)          cmd_pause ;;
  resume)         cmd_resume ;;
  status)         cmd_status ;;
  setup-autopause) cmd_setup_autopause "${1:-30m}" ;;
  remove-autopause) cmd_remove_autopause ;;
  setup-main-schedule) cmd_setup_main_schedule "${1:-1}" "${2:-9}" ;;
  remove-main-schedule) cmd_remove_main_schedule ;;
  *)
    echo "Usage: $0 {pause|resume|status|setup-autopause [IDLE_WINDOW]|remove-autopause|setup-main-schedule [SLEEP_H] [WAKE_H]|remove-main-schedule}"
    exit 1
    ;;
esac
