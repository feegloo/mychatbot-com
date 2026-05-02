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

# Optional overrides for Cloud Function deployment.
CF_ENV_FILE="${SCRIPT_DIR}/../../cloud-function/.env.gcp"
if [[ -f "$CF_ENV_FILE" ]]; then
  set -a
  source "$CF_ENV_FILE"
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
STATIC_BUCKET="${STATIC_BUCKET:-chatrag-static-${PROJECT_ID}}"
ENABLE_STATIC_CDN="${ENABLE_STATIC_CDN:-true}"
APP_DOMAIN="${APP_DOMAIN:-chatrag.app}"
WWW_APP_DOMAIN="${WWW_APP_DOMAIN:-www.chatrag.app}"

LB_IP_NAME="${LB_IP_NAME:-chatrag-lb-ip}"
LB_CERT_NAME="${LB_CERT_NAME:-chatrag-managed-cert}"
LB_NEG_NAME="${LB_NEG_NAME:-chatrag-api-neg}"
LB_API_BACKEND_SERVICE="${LB_API_BACKEND_SERVICE:-chatrag-api-backend}"
LB_STATIC_BACKEND_BUCKET="${LB_STATIC_BACKEND_BUCKET:-chatrag-static-backend}"
LB_URL_MAP="${LB_URL_MAP:-chatrag-url-map}"
LB_HTTPS_PROXY="${LB_HTTPS_PROXY:-chatrag-https-proxy}"
LB_HTTPS_FORWARDING_RULE="${LB_HTTPS_FORWARDING_RULE:-chatrag-https-fr}"

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
REPLICATE_API_TOKEN="${REPLICATE_API_TOKEN:-}"
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-}"
VITE_STRIPE_PUBLISHABLE_KEY="${VITE_STRIPE_PUBLISHABLE_KEY:-}"
VITE_API_BASE_URL="${VITE_API_BASE_URL:-}"
VITE_SENTRY_DSN="${VITE_SENTRY_DSN:-}"
GIT_COMMIT_HASH="${GIT_COMMIT_HASH:-$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)}"
DEPLOY_CLOUD_FUNCTION="${DEPLOY_CLOUD_FUNCTION:-false}"
CLOUD_FUNCTION_NAME="${CLOUD_FUNCTION_NAME:-chatrag-upload}"
CLOUD_FUNCTION_REGION="${CLOUD_FUNCTION_REGION:-$REGION}"
CLOUD_FUNCTION_RUNTIME="${CLOUD_FUNCTION_RUNTIME:-nodejs22}"
CF_PUBLIC_APP_BASE_URL="${CF_PUBLIC_APP_BASE_URL:-https://chatrag.app}"
CF_ALLOWED_ORIGINS="${CF_ALLOWED_ORIGINS:-https://chatrag.app,https://www.chatrag.app}"
CF_UPSTREAM_UPLOAD_URL="${CF_UPSTREAM_UPLOAD_URL:-}"
CF_SENTRY_DSN="${CF_SENTRY_DSN:-${SENTRY_DSN:-}}"
CF_SENTRY_ENVIRONMENT="${CF_SENTRY_ENVIRONMENT:-${SENTRY_ENVIRONMENT:-prod}}"
USER_WIKI_ENABLED="${USER_WIKI_ENABLED:-false}"
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
# In CI the vars are injected as environment variables; the file is only needed locally.
if [[ -f "infra/cloudrun/.env.gcp" ]]; then
  set -a
  source infra/cloudrun/.env.gcp
  set +a
fi

# ── Pre-flight checks ───────────────────────────────────────────────────────
[[ -z "$PROJECT_ID" ]] && error "Set GCP_PROJECT_ID env var first:\n  export GCP_PROJECT_ID=my-project-id"
[[ -z "$OPENAI_API_KEY" ]] && error "Set OPENAI_API_KEY env var"
[[ -z "$REPLICATE_API_TOKEN" ]] && warn "REPLICATE_API_TOKEN not set — /generate-video and /generate-music will fail at runtime"

# ── Step 1: Install prerequisites ────────────────────────────────────────────
info "Step 1/8: Checking prerequisites..."

# In CI (GitHub Actions) all tools are pre-installed; skip macOS/brew setup.
if [[ -z "${CI:-}" ]]; then
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

  if ! command -v npm &>/dev/null; then
    warn "Installing Node.js (npm required for cloud-function build)..."
    brew install node
  fi
fi

# ── Step 2: Authenticate & set project ───────────────────────────────────────
info "Step 2/8: Authenticating with GCP..."
if ! gcloud auth print-access-token &>/dev/null; then
  gcloud auth login --quiet 2>/dev/null || true
fi
gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com \
  cloudfunctions.googleapis.com \
  artifactregistry.googleapis.com \
  eventarc.googleapis.com \
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
if ! gcloud storage buckets describe "gs://${GCS_BUCKET}" &>/dev/null; then
  gcloud storage buckets create "gs://${GCS_BUCKET}" --location="$REGION"
  info "  Created bucket: ${GCS_BUCKET}"
else
  warn "  Bucket ${GCS_BUCKET} already exists, skipping."
fi

# Apply CORS so the browser can fetch signed URLs directly from storage.googleapis.com
# (needed for PDF embeds and range requests served via redirect from /api/storage).
CORS_FILE="${SCRIPT_DIR}/gcs-cors.json"
if [[ -f "$CORS_FILE" ]]; then
  gcloud storage buckets update "gs://${GCS_BUCKET}" --cors-file="$CORS_FILE"
  info "  Applied CORS config to bucket ${GCS_BUCKET}"
else
  warn "  CORS config file not found at ${CORS_FILE}, skipping."
fi

# ── Step 6: Build Docker image ───────────────────────────────────────────────
info "Step 6/9: Building Docker image..."

# Build frontend dist locally so we can sync static files to Cloud CDN bucket.
info "Step 6a/9: Building frontend dist for Cloud CDN..."
pushd frontend >/dev/null
npm ci
npm run build
popd >/dev/null

gcloud auth configure-docker --quiet
docker build \
  --build-arg VITE_STRIPE_PUBLISHABLE_KEY="${VITE_STRIPE_PUBLISHABLE_KEY}" \
  --build-arg VITE_API_BASE_URL="${VITE_API_BASE_URL}" \
  --build-arg VITE_SENTRY_DSN="${VITE_SENTRY_DSN}" \
  --build-arg VITE_COMMIT_HASH="${GIT_COMMIT_HASH}" \
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

# ── Step 8a: Pub/Sub skipped — inline worker mode ────────────────────────────
# Indexing runs in-process on the single Cloud Run instance (WORKER_MODE=inline).
# No Pub/Sub topic or chatrag-worker needed.
info "Step 8a/9: Skipped Pub/Sub setup (WORKER_MODE=inline)"

gcloud run deploy "$SERVICE_NAME" \
  --image "${IMAGE}:latest" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --network default \
  --subnet default \
  --vpc-egress private-ranges-only \
  --port 8080 \
  --memory 4Gi \
  --cpu 4 \
  --cpu-boost \
  --timeout=600 \
  --min-instances 0 \
  --max-instances 1 \
  --startup-probe "httpGet.path=/health,httpGet.port=8080,initialDelaySeconds=10,periodSeconds=10,timeoutSeconds=5,failureThreshold=20" \
  --set-env-vars "\
NODE_ENV=production,\
DATABASE_URL=${DATABASE_URL},\
CHROMA_MODE=local,\
ANONYMIZED_TELEMETRY=False,\
OTEL_ENABLED=false,\
OTEL_SDK_DISABLED=true,\
OPENAI_API_KEY=${OPENAI_API_KEY},\
REPLICATE_API_TOKEN=${REPLICATE_API_TOKEN},\
STORAGE_PROVIDER=gcs,
GCS_BUCKET=${GCS_BUCKET},
PYTHON_BIN=/app/python/.venv/bin/python3,\
PYTHON_PROJECT_ROOT=/app/python,\
PYTHON_SERVER_URL=http://localhost:8321,\
DEBUG_USER=${DEBUG_USER:-chatrag},\
DEBUG_PASS=${DEBUG_PASS:-chatragadmin},\
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY},\
WORKER_MODE=inline"

# ── Step 8b: Deploy chatrag-worker (Cloud Run Worker Pool, Pub/Sub-driven) ──
# Lightweight Python-only container (no Node, no frontend) that pulls from
# the indexing Pub/Sub subscription and processes whole PDFs. Deployed as a
# Cloud Run *Worker Pool* (no HTTP ingress, no request-driven scaling) —
# idle replicas fetch the next message themselves after ACKing the previous
# one. Enabled by default; set DEPLOY_WORKER=false to skip.
WORKER_SERVICE_NAME="chatrag-worker"
WORKER_IMAGE="gcr.io/${PROJECT_ID}/${WORKER_SERVICE_NAME}"

if [[ "${DEPLOY_WORKER:-false}" == "true" ]]; then
  info "Step 8b/9: Building + deploying ${WORKER_SERVICE_NAME} (Worker Pool)..."

  # Lightweight image — Python only, no frontend.
  docker build -f python/Dockerfile.worker -t "${WORKER_IMAGE}:latest" python/
  docker push "${WORKER_IMAGE}:latest"

  # Preserve the current instance count so a paused worker stays paused after deploy.
  # Only fall back to WORKER_INSTANCES if the pool doesn't exist yet.
  CURRENT_WORKER_INSTANCES=$(gcloud beta run worker-pools describe "$WORKER_SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --format="value(scaling.manualInstanceCount)" 2>/dev/null || echo "")
  if [[ -n "$CURRENT_WORKER_INSTANCES" ]]; then
    EFFECTIVE_WORKER_INSTANCES="$CURRENT_WORKER_INSTANCES"
    info "  Preserving current instance count: ${EFFECTIVE_WORKER_INSTANCES} (worker stays $([ "$EFFECTIVE_WORKER_INSTANCES" = "0" ] && echo "PAUSED" || echo "RUNNING"))"
  else
    EFFECTIVE_WORKER_INSTANCES="${WORKER_INSTANCES:-0}"
    info "  Worker pool not found — creating with ${EFFECTIVE_WORKER_INSTANCES} instance(s)"
  fi

  gcloud beta run worker-pools deploy "$WORKER_SERVICE_NAME" \
    --image "${WORKER_IMAGE}:latest" \
    --region "$REGION" \
    --network default \
    --subnet default \
    --vpc-egress private-ranges-only \
    --memory 1Gi \
    --cpu 1 \
    --instances "${EFFECTIVE_WORKER_INSTANCES}" \
    --set-env-vars "\
PYTHONUNBUFFERED=1,\
GCP_PROJECT_ID=${GCP_PROJECT_ID},\
PUBSUB_TOPIC=${PUBSUB_TOPIC},\
PUBSUB_SUBSCRIPTION=${PUBSUB_SUBSCRIPTION},\
PUBSUB_MAX_MESSAGES=1,\
DATABASE_URL=${DATABASE_URL},\
CHROMA_MODE=local,\
ANONYMIZED_TELEMETRY=False,\
OTEL_ENABLED=false,\
OTEL_SDK_DISABLED=true,\
OPENAI_API_KEY=${OPENAI_API_KEY},\
STORAGE_PROVIDER=gcs,\
GCS_BUCKET=${GCS_BUCKET},\
WORKER_MODE=pubsub_worker,\
SENTRY_DSN=${SENTRY_DSN:-},\
SENTRY_ENVIRONMENT=prod"

  info "  ${WORKER_SERVICE_NAME} worker pool deployed (pulling ${PUBSUB_SUBSCRIPTION})"
else
  warn "Step 8b/9: Skipping chatrag-worker deployment (DEPLOY_WORKER=false)"
fi

# ── Step 8c: Sync frontend static dist to Cloud CDN bucket ───────────────────
if [[ "${ENABLE_STATIC_CDN}" == "true" ]]; then
  info "Step 8c/9: Syncing frontend dist to Cloud CDN bucket..."

  gcloud services enable storage.googleapis.com

  if ! gcloud storage buckets describe "gs://${STATIC_BUCKET}" &>/dev/null; then
    gcloud storage buckets create "gs://${STATIC_BUCKET}" --location="$REGION"
    info "  Created static bucket: ${STATIC_BUCKET}"
  else
    warn "  Static bucket ${STATIC_BUCKET} already exists, reusing."
  fi

  # Public read access for CDN backend bucket origin.
  #
  # WHY gsutil instead of gcloud:
  #   GCS buckets created in some projects default to `public_access_prevention: enforced`,
  #   which blocks allUsers IAM bindings even when explicitly granted — causing 403
  #   "AccessDenied" from the CDN backend bucket regardless of IAM policy.
  #   `gcloud storage buckets update --clear-pap` silently failed to lift this in
  #   practice (2026-05-01 incident: chatrag.app returned 403 after CDN migration).
  #   `gsutil pap set unspecified` correctly sets PAP to "inherited" (= no restriction)
  #   without requiring the Organization Policy API to be enabled on the project.
  gsutil pap set unspecified "gs://${STATIC_BUCKET}" || true
  gcloud storage buckets add-iam-policy-binding "gs://${STATIC_BUCKET}" \
    --member="allUsers" \
    --role="roles/storage.objectViewer" || true

  gcloud storage buckets update "gs://${STATIC_BUCKET}" \
    --web-main-page-suffix=index.html \
    --web-error-page=index.html || true

  gcloud storage rsync \
    --recursive \
    --delete-unmatched-destination-objects \
    frontend/dist "gs://${STATIC_BUCKET}"

  # HTML should revalidate, hashed assets can be cached aggressively.
  gcloud storage objects update "gs://${STATIC_BUCKET}/index.html" \
    --cache-control="no-cache, max-age=0, must-revalidate" || true
  gcloud storage objects update "gs://${STATIC_BUCKET}/assets/**" \
    --recursive \
    --cache-control="public, max-age=31536000, immutable" || true
  gcloud storage objects update "gs://${STATIC_BUCKET}/*.png" "gs://${STATIC_BUCKET}/*.svg" \
    --cache-control="public, max-age=86400" || true
fi

# ── Step 8d: Configure HTTPS LB: static by default, /api/* to Cloud Run ─────
if [[ "${ENABLE_STATIC_CDN}" == "true" ]]; then
  info "Step 8d/9: Configuring HTTPS Load Balancer + Cloud CDN routing..."

  if ! gcloud compute network-endpoint-groups describe "$LB_NEG_NAME" --region "$REGION" &>/dev/null; then
    gcloud compute network-endpoint-groups create "$LB_NEG_NAME" \
      --region "$REGION" \
      --network-endpoint-type=serverless \
      --cloud-run-service "$SERVICE_NAME"
    info "  Created serverless NEG: ${LB_NEG_NAME}"
  else
    warn "  Serverless NEG ${LB_NEG_NAME} already exists, reusing."
  fi

  if ! gcloud compute backend-services describe "$LB_API_BACKEND_SERVICE" --global &>/dev/null; then
    gcloud compute backend-services create "$LB_API_BACKEND_SERVICE" \
      --global \
      --load-balancing-scheme=EXTERNAL_MANAGED
    info "  Created API backend service: ${LB_API_BACKEND_SERVICE}"
  else
    # Serverless NEGs cannot be attached when backend service has portName set.
    # Strip portName via export/import so we don't need to detach the url-map.
    EXISTING_PORT_NAME=$(gcloud compute backend-services describe "$LB_API_BACKEND_SERVICE" --global --format='value(portName)' || true)
    if [[ -n "$EXISTING_PORT_NAME" ]]; then
      warn "  Stripping portName='${EXISTING_PORT_NAME}' from API backend service for serverless NEG compatibility..."
      TMP_BS_FILE="$(mktemp)"
      gcloud compute backend-services export "$LB_API_BACKEND_SERVICE" --global --destination="$TMP_BS_FILE"
      # Remove the portName line in-place (BSD/GNU sed compatible)
      sed -i.bak '/^portName:/d' "$TMP_BS_FILE" && rm -f "${TMP_BS_FILE}.bak"
      gcloud compute backend-services import "$LB_API_BACKEND_SERVICE" --global --source="$TMP_BS_FILE" --quiet
      rm -f "$TMP_BS_FILE"
      info "  Cleared portName on API backend service: ${LB_API_BACKEND_SERVICE}"
    fi
  fi

  if ! gcloud compute backend-services describe "$LB_API_BACKEND_SERVICE" --global --format='value(backends.group)' | grep -q "/networkEndpointGroups/${LB_NEG_NAME}$"; then
    gcloud compute backend-services add-backend "$LB_API_BACKEND_SERVICE" \
      --global \
      --network-endpoint-group "$LB_NEG_NAME" \
      --network-endpoint-group-region "$REGION"
    info "  Attached NEG to API backend service"
  fi

  if ! gcloud compute backend-buckets describe "$LB_STATIC_BACKEND_BUCKET" --global &>/dev/null; then
    gcloud compute backend-buckets create "$LB_STATIC_BACKEND_BUCKET" \
      --gcs-bucket-name "$STATIC_BUCKET" \
      --enable-cdn
    info "  Created static backend bucket: ${LB_STATIC_BACKEND_BUCKET}"
  else
    gcloud compute backend-buckets update "$LB_STATIC_BACKEND_BUCKET" --enable-cdn
  fi

  TMP_URL_MAP_FILE="$(mktemp)"
  cat > "$TMP_URL_MAP_FILE" <<EOF
name: ${LB_URL_MAP}
defaultService: https://www.googleapis.com/compute/v1/projects/${PROJECT_ID}/global/backendBuckets/${LB_STATIC_BACKEND_BUCKET}
hostRules:
  - hosts:
      - ${APP_DOMAIN}
      - ${WWW_APP_DOMAIN}
    pathMatcher: chatrag-paths
pathMatchers:
  - name: chatrag-paths
    defaultService: https://www.googleapis.com/compute/v1/projects/${PROJECT_ID}/global/backendBuckets/${LB_STATIC_BACKEND_BUCKET}
    pathRules:
      - paths:
          - /api/*
        service: https://www.googleapis.com/compute/v1/projects/${PROJECT_ID}/global/backendServices/${LB_API_BACKEND_SERVICE}
EOF

  gcloud compute url-maps import "$LB_URL_MAP" \
    --global \
    --source "$TMP_URL_MAP_FILE" \
    --quiet
  rm -f "$TMP_URL_MAP_FILE"

  if ! gcloud compute ssl-certificates describe "$LB_CERT_NAME" --global &>/dev/null; then
    gcloud compute ssl-certificates create "$LB_CERT_NAME" \
      --domains "${APP_DOMAIN},${WWW_APP_DOMAIN}" \
      --global
    info "  Created managed SSL certificate: ${LB_CERT_NAME}"
  else
    warn "  Managed SSL certificate ${LB_CERT_NAME} already exists, reusing."
  fi

  if ! gcloud compute target-https-proxies describe "$LB_HTTPS_PROXY" --global &>/dev/null; then
    gcloud compute target-https-proxies create "$LB_HTTPS_PROXY" \
      --url-map "$LB_URL_MAP" \
      --ssl-certificates "$LB_CERT_NAME"
  else
    gcloud compute target-https-proxies update "$LB_HTTPS_PROXY" \
      --url-map "$LB_URL_MAP" \
      --ssl-certificates "$LB_CERT_NAME"
  fi

  if ! gcloud compute addresses describe "$LB_IP_NAME" --global &>/dev/null; then
    gcloud compute addresses create "$LB_IP_NAME" --global
    info "  Created global IP address: ${LB_IP_NAME}"
  fi
  LB_IP_ADDRESS=$(gcloud compute addresses describe "$LB_IP_NAME" --global --format='value(address)')

  if ! gcloud compute forwarding-rules describe "$LB_HTTPS_FORWARDING_RULE" --global &>/dev/null; then
    gcloud compute forwarding-rules create "$LB_HTTPS_FORWARDING_RULE" \
      --global \
      --load-balancing-scheme=EXTERNAL_MANAGED \
      --network-tier=PREMIUM \
      --address "$LB_IP_NAME" \
      --target-https-proxy "$LB_HTTPS_PROXY" \
      --ports 443
    info "  Created HTTPS forwarding rule: ${LB_HTTPS_FORWARDING_RULE}"
  else
    gcloud compute forwarding-rules set-target "$LB_HTTPS_FORWARDING_RULE" \
      --global \
      --target-https-proxy "$LB_HTTPS_PROXY"
  fi
fi

# ── Step 9: Get URL ─────────────────────────────────────────────────────────
info "Step 9/10: Getting service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')

if [[ -z "$CF_UPSTREAM_UPLOAD_URL" ]]; then
  CF_UPSTREAM_UPLOAD_URL="${SERVICE_URL}/api/upload"
fi

# ── Step 10: Deploy Cloud Function upload proxy ────────────────────────────
FUNCTION_URL=""
if [[ "$DEPLOY_CLOUD_FUNCTION" == "true" ]]; then
  info "Step 10/10: Deploying Cloud Function ${CLOUD_FUNCTION_NAME}..."
  pushd "${SCRIPT_DIR}/../../cloud-function" >/dev/null
  npm ci
  npm run build

  gcloud functions deploy "$CLOUD_FUNCTION_NAME" \
    --gen2 \
    --runtime "$CLOUD_FUNCTION_RUNTIME" \
    --region "$CLOUD_FUNCTION_REGION" \
    --source . \
    --entry-point uploadProxy \
    --trigger-http \
    --allow-unauthenticated \
    --set-env-vars "^;^UPSTREAM_UPLOAD_URL=${CF_UPSTREAM_UPLOAD_URL};PUBLIC_APP_BASE_URL=${CF_PUBLIC_APP_BASE_URL};ALLOWED_ORIGINS=${CF_ALLOWED_ORIGINS};SENTRY_DSN=${CF_SENTRY_DSN};SENTRY_ENVIRONMENT=${CF_SENTRY_ENVIRONMENT}"

  FUNCTION_URL=$(gcloud functions describe "$CLOUD_FUNCTION_NAME" \
    --gen2 \
    --region "$CLOUD_FUNCTION_REGION" \
    --format='value(serviceConfig.uri)')
  popd >/dev/null
else
  warn "Step 10/10: Skipping Cloud Function deploy (DEPLOY_CLOUD_FUNCTION=false)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Deployed!${NC}  $SERVICE_URL"
echo "  DB password:    $DB_PASSWORD  (save this!)"
echo "  Worker mode:    inline (indexing runs in-process on this instance)"
echo "  Worker pool:    disabled"
if [[ "${ENABLE_STATIC_CDN}" == "true" ]]; then
  echo "  Static CDN:     enabled (GCS + Cloud CDN + HTTPS LB)"
  echo "  Static bucket:  gs://${STATIC_BUCKET}"
  echo "  API routing:    /api/* -> Cloud Run ${SERVICE_NAME}"
  if [[ -n "${LB_IP_ADDRESS:-}" ]]; then
    echo "  LB IP:          ${LB_IP_ADDRESS}"
    echo "  DNS apex A:     ${APP_DOMAIN} -> ${LB_IP_ADDRESS}"
    echo "  DNS www CNAME:  ${WWW_APP_DOMAIN} -> ${APP_DOMAIN}"
  fi
fi
if [[ -n "$FUNCTION_URL" ]]; then
  echo "  Function URL:   ${FUNCTION_URL}"
  echo "  UI env var:     VITE_CLOUD_FUNCTION_UPLOAD_URL=${FUNCTION_URL}/upload"
fi
echo "  PDF offload:    Pub/Sub pull → chatrag-worker pool (idle replicas fetch next job)"
echo "═══════════════════════════════════════════════════════════════"
