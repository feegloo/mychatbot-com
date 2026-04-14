#!/usr/bin/env bash
#
# deploy-gcp.sh — Deploy MyChatbot to Google Cloud Run (macOS)
#
# Usage:
#   chmod +x infra/cloudrun/deploy-gcp.sh
#   ./infra/cloudrun/deploy-gcp.sh
#
set -euo pipefail

# ── Configuration (edit these) ───────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="europe-west1"
SERVICE_NAME="mychatbot"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

DB_INSTANCE_NAME="chatrag-db"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 16)}"
DB_USER="mychatbot"
DB_NAME="mychatbot"

GCS_BUCKET="${GCS_BUCKET:-mychatbot-storage-${PROJECT_ID}}"

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
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
gcloud auth login --quiet 2>/dev/null || true
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
  gcloud sql instances create "$DB_INSTANCE_NAME" \
    --database-version=POSTGRES_16 \
    --edition=ENTERPRISE \
    --tier=db-custom-2-3840 \
    --region="$REGION" \
    --root-password="$DB_PASSWORD" \
    --storage-size=10GB \
    --storage-auto-increase \
    --assign-ip \
    --network=default
  info "  Created instance: $DB_INSTANCE_NAME"

  # Enable automatic daily backups at 03:00 UTC, keep last 2
  gcloud sql instances patch "$DB_INSTANCE_NAME" \
    --backup-start-time="03:00" \
    --retained-backups-count=2 \
    --quiet
  info "  Enabled automatic backups"
else
  warn "  Instance $DB_INSTANCE_NAME already exists, skipping."
fi

# Create database and user
gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE_NAME" 2>/dev/null || true
gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE_NAME" --password="$DB_PASSWORD" 2>/dev/null || true

# Get connection name for Cloud Run
DB_CONNECTION_NAME=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format='value(connectionName)')
info "  Connection name: $DB_CONNECTION_NAME"

# ── Step 4: Initialize database schema ───────────────────────────────────────
info "Step 4/8: Getting Cloud SQL instance details..."

# Get the public IP of the instance using jq to parse JSON
DB_PUBLIC_IP=$(gcloud sql instances describe "$DB_INSTANCE_NAME" \
  --format=json 2>/dev/null | jq -r '.ipAddresses[] | select(.type=="PRIMARY") | .ipAddress' | head -1)

if [[ -z "$DB_PUBLIC_IP" ]]; then
  error "Could not get public IP. Ensure instance has public IP enabled with: gcloud sql instances patch $DB_INSTANCE_NAME --assign-ip"
fi

info "  Cloud SQL public IP: $DB_PUBLIC_IP"

# Allow all IPs for now (needed for Cloud Run to connect)
warn "  Setting firewall to allow 0.0.0.0/0..."
gcloud sql instances patch "$DB_INSTANCE_NAME" \
  --authorized-networks=0.0.0.0/0 \
  --quiet || error "Could not update firewall rules"

info "  Firewall updated"

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
docker build -t "${IMAGE}:latest" .

# ── Step 7: Push to GCR ─────────────────────────────────────────────────────
info "Step 7/9: Pushing image to Container Registry..."
docker push "${IMAGE}:latest"

# ── Step 8: Deploy to Cloud Run ──────────────────────────────────────────────
info "Step 8/9: Deploying to Cloud Run..."

DATABASE_URL="postgres://${DB_USER}:${DB_PASSWORD}@${DB_PUBLIC_IP}:5432/${DB_NAME}"

warn "  DATABASE_URL: postgres://${DB_USER}:****@${DB_PUBLIC_IP}:5432/${DB_NAME}"

gcloud run deploy "$SERVICE_NAME" \
  --image "${IMAGE}:latest" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 300 \
  --set-env-vars "\
NODE_ENV=production,\
DATABASE_URL=${DATABASE_URL},\
CHROMA_MODE=local,\
OPENAI_API_KEY=${OPENAI_API_KEY},\
STORAGE_PROVIDER=gcs,
GCS_BUCKET=${GCS_BUCKET},
FRONTEND_DIST_PATH=/app/frontend/dist,\
PYTHON_BIN=/app/python/.venv/bin/python3,\
PYTHON_PROJECT_ROOT=/app/python,\
PYTHON_SERVER_URL=http://localhost:8321"

# ── Step 9: Get URL ─────────────────────────────────────────────────────────
info "Step 9/9: Getting service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Deployed!${NC}  $SERVICE_URL"
echo "  DB password: $DB_PASSWORD  (save this!)"
echo "═══════════════════════════════════════════════════════════════"
