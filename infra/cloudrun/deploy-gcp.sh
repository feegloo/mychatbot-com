#!/usr/bin/env bash
#
# deploy-gcp.sh — Deploy ChatRAG to Google Cloud Run (macOS)
#
# Usage:
#   chmod +x infra/cloudrun/deploy-gcp.sh
#   ./infra/cloudrun/deploy-gcp.sh
#
set -euo pipefail

# ── Load .env.gcp if present ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.gcp"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# ── Configuration (edit these) ───────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="europe-west1"
SERVICE_NAME="chatrag"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

DB_INSTANCE_NAME="chatrag-db-instance"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 16)}"
DB_USER="chatrag"
DB_NAME="chatrag"

GCS_BUCKET="${GCS_BUCKET:-chatrag-storage-${PROJECT_ID}}"

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-}"
VITE_STRIPE_PUBLISHABLE_KEY="${VITE_STRIPE_PUBLISHABLE_KEY:-}"
# Chroma Cloud — no longer used (switched to in-process local Chroma for lowest latency)
# CHROMA_API_KEY="${CHROMA_API_KEY:-}"
# CHROMA_TENANT="696cf798-1423-4a5f-bb61-c055be3b6318"
# CHROMA_DATABASE="chatbotqa"

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Init env ─────────────────────────────────────────────────────────────────
source infra/cloudrun/.env.gcp

# ── Pre-flight checks ───────────────────────────────────────────────────────
[[ -z "$PROJECT_ID" ]] && error "Set GCP_PROJECT_ID env var first:\n  export GCP_PROJECT_ID=my-project-id"
[[ -z "$OPENAI_API_KEY" ]] && error "Set OPENAI_API_KEY env var"

# ── Step 1: Install prerequisites ────────────────────────────────────────────
info "Step 1/8: Checking prerequisites..."

if ! command -v brew &>/dev/null; then
  warn "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

if ! command -v gcloud &>/dev/null; then
  warn "Installing Google Cloud SDK..."
  brew install --cask google-cloud-sdk
fi

if ! command -v docker &>/dev/null; then
  warn "Installing Docker..."
  brew install --cask docker
  echo "Please start Docker Desktop, then re-run this script."
  exit 1
fi

# ── Step 2: Authenticate & set project ───────────────────────────────────────
info "Step 2/8: Authenticating with GCP..."
if ! gcloud auth print-access-token &>/dev/null; then
  gcloud auth login --quiet 2>/dev/null || true
fi
gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com

# ── Step 2b: Set up Private Service Connection ───────────────────────────────
info "Step 2b/8: Setting up Private Service Connection..."
if ! gcloud compute addresses describe google-managed-services-default --global &>/dev/null; then
  warn "  Creating private connection address..."
  gcloud compute addresses create google-managed-services-default \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --network=default
fi

if ! gcloud services vpc-peerings list --service=servicenetworking.googleapis.com 2>/dev/null | grep -q "servicenetworking-googleapis-com"; then
  warn "  Creating VPC peering connection..."
  gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-default \
    --network=default
fi
info "  Private Service Connection ready"

# ── Step 3: Create Cloud SQL PostgreSQL instance ─────────────────────────────
info "Step 3/8: Creating Cloud SQL PostgreSQL instance..."
if ! gcloud sql instances describe "$DB_INSTANCE_NAME" --project="$PROJECT_ID" &>/dev/null; then
  # Cheapest option: --tier=db-f1-micro (shared core, 0.6 GiB, ~$8/mo, no SLA)
  # db-custom-2-3840
  gcloud sql instances create "$DB_INSTANCE_NAME" \
    --database-version=POSTGRES_16 \
    --edition=ENTERPRISE \
    --tier=db-f1-micro \
    --region="$REGION" \
    --root-password="$DB_PASSWORD" \
    --storage-size=10GB \
    --storage-auto-increase \
    --no-assign-ip \
    --network=default
  info "  Created instance: $DB_INSTANCE_NAME"

  # Enable automatic daily backups at 03:00 UTC, keep last 2
  gcloud sql instances patch "$DB_INSTANCE_NAME" \
    --backup-start-time="03:00" \
    --retained-backups-count=1 \
    --quiet
  info "  Enabled automatic backups"
else
  warn "  Instance $DB_INSTANCE_NAME already exists, skipping."
fi

# Create database and user (if they don't already exist)
if ! gcloud sql databases describe "$DB_NAME" --instance="$DB_INSTANCE_NAME" &>/dev/null; then
  gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE_NAME"
  info "  Created database $DB_NAME"
else
  warn "  Database $DB_NAME already exists, skipping."
fi
if ! gcloud sql users list --instance="$DB_INSTANCE_NAME" --format='value(name)' | grep -qx "$DB_USER"; then
  gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE_NAME" --password="$DB_PASSWORD"
  info "  Created user $DB_USER"
else
  warn "  User $DB_USER already exists, skipping."
fi

# Get connection name for Cloud Run
DB_CONNECTION_NAME=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format='value(connectionName)')
info "  Connection name: $DB_CONNECTION_NAME"

# ── Step 4: Initialize database schema ───────────────────────────────────────
info "Step 4/8: Getting Cloud SQL instance details..."

# Get the private IP of the instance (private IP only, no public IP)
DB_PRIVATE_IP=$(gcloud sql instances describe "$DB_INSTANCE_NAME" \
  --format=json 2>/dev/null | jq -r '.ipAddresses[] | select(.type=="PRIVATE") | .ipAddress' | head -1)

if [[ -z "$DB_PRIVATE_IP" ]]; then
  error "Could not get private IP. Ensure instance has private IP enabled and VPC peering is configured."
fi

info "  Cloud SQL private IP: $DB_PRIVATE_IP"

# ── Step 5: Create GCS bucket for file storage ──────────────────────────────
info "Step 5/9: Creating GCS bucket for file storage..."
gcloud services enable storage.googleapis.com
if ! gsutil ls -b "gs://${GCS_BUCKET}" &>/dev/null; then
  gsutil mb -l "$REGION" "gs://${GCS_BUCKET}"
  info "  Created bucket: ${GCS_BUCKET}"
else
  warn "  Bucket ${GCS_BUCKET} already exists, skipping."
fi

# ── Step 6: Build Docker image ───────────────────────────────────────────────
info "Step 6/9: Building Docker image..."
gcloud auth configure-docker --quiet
docker build \
  --build-arg VITE_STRIPE_PUBLISHABLE_KEY="${VITE_STRIPE_PUBLISHABLE_KEY}" \
  --build-arg SENTRY_AUTH_TOKEN="${SENTRY_AUTH_TOKEN}" \
  --build-arg SENTRY_ORG="${SENTRY_ORG}" \
  --build-arg SENTRY_PROJECT="${SENTRY_PROJECT}" \
  -t "${IMAGE}:latest" .

# ── Step 7: Push to GCR ─────────────────────────────────────────────────────
info "Step 7/9: Pushing image to Container Registry..."
docker push "${IMAGE}:latest"

# ── Step 8: Deploy to Cloud Run ──────────────────────────────────────────────
info "Step 8/9: Deploying to Cloud Run..."

DATABASE_URL="postgres://${DB_USER}:${DB_PASSWORD}@${DB_PRIVATE_IP}:5432/${DB_NAME}"

warn "  DATABASE_URL: postgres://${DB_USER}:****@${DB_PRIVATE_IP}:5432/${DB_NAME}"

# Generate a shared secret for the indexer if not already set
INDEXER_SECRET="${INDEXER_SECRET:-$(openssl rand -hex 32)}"

gcloud run deploy "$SERVICE_NAME" \
  --image "${IMAGE}:latest" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --network default \
  --subnet default \
  --vpc-egress private-ranges-only \
  --port 8080 \
  --memory 16Gi \
  --cpu 8 \
  --min-instances 2 \
  --max-instances 4 \
  --timeout 300 \
  --set-env-vars "\
NODE_ENV=production,\
DATABASE_URL=${DATABASE_URL},\
CHROMA_MODE=local,\
ANONYMIZED_TELEMETRY=False,\
OTEL_ENABLED=false,\
OTEL_SDK_DISABLED=true,\
OPENAI_API_KEY=${OPENAI_API_KEY},\
STORAGE_PROVIDER=gcs,
GCS_BUCKET=${GCS_BUCKET},
FRONTEND_DIST_PATH=/app/frontend/dist,\
PYTHON_BIN=/app/python/.venv/bin/python3,\
PYTHON_PROJECT_ROOT=/app/python,\
PYTHON_SERVER_URL=http://localhost:8321,\
USE_GEMMA=${USE_GEMMA:-false},\
GEMMA_MODEL=${GEMMA_MODEL:-gemma4},\
GEMMA_BASE_URL=${GEMMA_BASE_URL:-http://localhost:11434},\
DEBUG_USER=${DEBUG_USER:-chatrag},\
DEBUG_PASS=${DEBUG_PASS:-chatragadmin},\
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY},\
WORKER_MODE=${WORKER_MODE:-local},\
WORKER_JOB_NAME=${WORKER_JOB_NAME:-chatrag-worker},\
WORKER_REGION=${WORKER_REGION:-europe-west1},\
GCP_PROJECT_ID=${GCP_PROJECT_ID},\
INDEXER_SECRET=${INDEXER_SECRET}"

# ── Step 8b: Deploy chatrag-indexer service ─────────────────────────────────
info "Step 8b/9: Deploying chatrag-indexer (dedicated PDF worker)..."

INDEXER_SERVICE_NAME="chatrag-indexer"

gcloud run deploy "$INDEXER_SERVICE_NAME" \
  --image "${IMAGE}:latest" \
  --region "$REGION" \
  --platform managed \
  --no-allow-unauthenticated \
  --ingress internal-and-cloud-load-balancing \
  --network default \
  --subnet default \
  --vpc-egress private-ranges-only \
  --port 8080 \
  --memory 4Gi \
  --cpu 4 \
  --min-instances 1 \
  --max-instances 2 \
  --concurrency 4 \
  --timeout 600 \
  --set-env-vars "\
NODE_ENV=production,\
DATABASE_URL=${DATABASE_URL},\
CHROMA_MODE=local,\
ANONYMIZED_TELEMETRY=False,\
OTEL_ENABLED=false,\
OTEL_SDK_DISABLED=true,\
OPENAI_API_KEY=${OPENAI_API_KEY},\
STORAGE_PROVIDER=gcs,\
GCS_BUCKET=${GCS_BUCKET},\
FRONTEND_DIST_PATH=,\
PYTHON_BIN=/app/python/.venv/bin/python3,\
PYTHON_PROJECT_ROOT=/app/python,\
PYTHON_SERVER_URL=http://localhost:8321,\
WORKER_MODE=local,\
GCP_PROJECT_ID=${GCP_PROJECT_ID},\
INDEXER_SECRET=${INDEXER_SECRET}"

INDEXER_URL=$(gcloud run services describe "$INDEXER_SERVICE_NAME" --region "$REGION" --format='value(status.url)')
info "  chatrag-indexer deployed at: ${INDEXER_URL}"

# Wire the indexer URL back into the main service
info "  Updating chatrag with INDEXER_URL..."
gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --update-env-vars "INDEXER_URL=${INDEXER_URL}"

# ── Step 9: Get URL ─────────────────────────────────────────────────────────
info "Step 9/9: Getting service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Deployed!${NC}  $SERVICE_URL"
echo "  DB password:    $DB_PASSWORD  (save this!)"
echo "  Indexer URL:    $INDEXER_URL  (internal only)"
echo "  Indexer secret: $INDEXER_SECRET  (save this!)"
echo "  Min instances:  2 (chatrag), 1 (chatrag-indexer)"
echo "  PDF offload:    50% of uploads delegated to chatrag-indexer"
echo "═══════════════════════════════════════════════════════════════"
