#!/usr/bin/env bash
#
# setup-pubsub.sh — Create the Pub/Sub topic + subscription used to
# delegate PDF indexing from the main chatrag service to chatrag-worker.
#
# Idempotent: safe to re-run. Invoked from infra/cloudrun/deploy-gcp.sh.
#
# Usage:
#   ./infra/pubsub/setup.sh [PROJECT_ID]
#
# Env overrides:
#   PUBSUB_TOPIC             default: chatrag-indexing
#   PUBSUB_SUBSCRIPTION      default: chatrag-indexing-sub
#   PUBSUB_DLQ_TOPIC         default: chatrag-indexing-dlq
#   PUBSUB_ACK_DEADLINE      default: 600 (seconds — matches large PDF time)
#   PUBSUB_MAX_DELIVERY_ATT  default: 2 (original + 1 retry, then → DLQ)
set -euo pipefail

PROJECT_ID="${1:-${GCP_PROJECT_ID:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 <PROJECT_ID>  (or export GCP_PROJECT_ID)" >&2
  exit 1
fi

TOPIC="${PUBSUB_TOPIC:-chatrag-indexing}"
SUB="${PUBSUB_SUBSCRIPTION:-chatrag-indexing-sub}"
DLQ_TOPIC="${PUBSUB_DLQ_TOPIC:-chatrag-indexing-dlq}"
DLQ_SUB="${DLQ_TOPIC}-sub"
ACK_DEADLINE="${PUBSUB_ACK_DEADLINE:-600}"
MAX_DELIVERY="${PUBSUB_MAX_DELIVERY_ATT:-2}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable pubsub.googleapis.com --project="$PROJECT_ID" >/dev/null

# ── Main topic + DLQ topic ───────────────────────────────────────────
if ! gcloud pubsub topics describe "$TOPIC" --project="$PROJECT_ID" &>/dev/null; then
  gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID"
  info "Created topic $TOPIC"
else
  warn "Topic $TOPIC already exists — skipping"
fi

if ! gcloud pubsub topics describe "$DLQ_TOPIC" --project="$PROJECT_ID" &>/dev/null; then
  gcloud pubsub topics create "$DLQ_TOPIC" --project="$PROJECT_ID"
  info "Created DLQ topic $DLQ_TOPIC"
else
  warn "DLQ topic $DLQ_TOPIC already exists — skipping"
fi

# ── Main subscription (pull) ─────────────────────────────────────────
# Workers pull messages. Ack deadline is long enough for large PDFs,
# and the subscriber client extends it automatically while processing.
if ! gcloud pubsub subscriptions describe "$SUB" --project="$PROJECT_ID" &>/dev/null; then
  gcloud pubsub subscriptions create "$SUB" \
    --topic="$TOPIC" \
    --ack-deadline="$ACK_DEADLINE" \
    --dead-letter-topic="$DLQ_TOPIC" \
    --dead-letter-topic-project="$PROJECT_ID" \
    --max-delivery-attempts="$MAX_DELIVERY" \
    --min-retry-delay=10s \
    --max-retry-delay=600s \
    --project="$PROJECT_ID"
  info "Created subscription $SUB → $TOPIC (DLQ=$DLQ_TOPIC, ack=${ACK_DEADLINE}s)"
else
  # Subscription exists — idempotently re-apply retry config so changes
  # to PUBSUB_MAX_DELIVERY_ATT / retry delays in this file take effect
  # on the live subscription without requiring a full recreate.
  gcloud pubsub subscriptions update "$SUB" \
    --ack-deadline="$ACK_DEADLINE" \
    --dead-letter-topic="$DLQ_TOPIC" \
    --dead-letter-topic-project="$PROJECT_ID" \
    --max-delivery-attempts="$MAX_DELIVERY" \
    --min-retry-delay=10s \
    --max-retry-delay=600s \
    --project="$PROJECT_ID" >/dev/null
  info "Updated subscription $SUB (max-delivery=$MAX_DELIVERY, ack=${ACK_DEADLINE}s)"
fi

# DLQ subscription so we can inspect failed messages with gcloud.
if ! gcloud pubsub subscriptions describe "$DLQ_SUB" --project="$PROJECT_ID" &>/dev/null; then
  gcloud pubsub subscriptions create "$DLQ_SUB" \
    --topic="$DLQ_TOPIC" \
    --ack-deadline=60 \
    --project="$PROJECT_ID"
  info "Created DLQ subscription $DLQ_SUB"
else
  warn "DLQ subscription $DLQ_SUB already exists — skipping"
fi

# ── IAM for Pub/Sub service account DLQ forwarding ───────────────────
# Pub/Sub's managed service account needs permission to publish to the
# DLQ topic and acknowledge the main subscription on our behalf.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
PUBSUB_SA="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$DLQ_TOPIC" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/pubsub.publisher" \
  --project="$PROJECT_ID" >/dev/null 2>&1 || true

gcloud pubsub subscriptions add-iam-policy-binding "$SUB" \
  --member="serviceAccount:${PUBSUB_SA}" \
  --role="roles/pubsub.subscriber" \
  --project="$PROJECT_ID" >/dev/null 2>&1 || true

info "Pub/Sub setup complete."
echo
echo "  Topic:        projects/${PROJECT_ID}/topics/${TOPIC}"
echo "  Subscription: projects/${PROJECT_ID}/subscriptions/${SUB}"
echo "  DLQ:          projects/${PROJECT_ID}/topics/${DLQ_TOPIC}"
