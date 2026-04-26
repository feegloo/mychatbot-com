#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENVIRONMENT_NAME="${ENV:-prod}"
ENV_FILE="${SCRIPT_DIR}/.env.${ENVIRONMENT_NAME}"
PROXY_PID=""

# Print one readable deploy log line.
log() {
    echo "[chatrag:${ENVIRONMENT_NAME}] $*"
}

# Stop local Cloud SQL Auth Proxy if this script started it.
stop_cloud_sql_proxy() {
    if [[ -n "${PROXY_PID}" ]]; then
        kill "${PROXY_PID}" >/dev/null 2>&1 || true
    fi
}

# Load env vars for selected environment: infra/.env.dev or infra/.env.prod.
load_env() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Missing env file: ${ENV_FILE}" >&2
        echo "Use ENV=dev or ENV=prod." >&2
        exit 1
    fi

    set -a
    source "${ENV_FILE}"
    set +a
}

# Fail fast when one required env var is empty.
require_env() {
    local name="$1"
    local value="${!name:-}"

    if [[ -z "${value}" ]]; then
        echo "Missing required env: ${name} in ${ENV_FILE}" >&2
        exit 1
    fi
}

# Compute the default Gen2 Cloud Function URL used before custom domain migration.
default_upload_function_url() {
    echo "https://${GCP_REGION}-${GCP_PROJECT_ID}.cloudfunctions.net/${UPLOAD_FUNCTION_NAME}"
}

# Read GCP project number for internal Cloud Run URL hints and summary output.
get_project_number() {
    gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)'
}

# Derive build-time frontend URLs for Option A when they are left empty in env.
derive_frontend_envs() {
    if [[ -z "${VITE_UPLOAD_FUNCTION_URL:-}" ]]; then
        VITE_UPLOAD_FUNCTION_URL="$(default_upload_function_url)"
    fi

    if [[ -z "${VITE_APP_BASE_URL:-}" ]]; then
        VITE_APP_BASE_URL="https://${SERVER_SERVICE_NAME}-$(get_project_number).${GCP_REGION}.run.app"
    fi
}

# Validate all env values required for deployment.
require_all_envs() {
    local required=(
        ENVIRONMENT
        GCP_PROJECT_ID
        GCP_REGION
        GOOGLE_APPLICATION_CREDENTIALS
        PUBLIC_APP_DOMAIN
        ALLOWED_ORIGINS
        SERVER_SERVICE_NAME
        UPLOAD_FUNCTION_NAME
        WORKER_POOL_NAME
        GCS_BUCKET
        PUBSUB_TOPIC
        PUBSUB_SUBSCRIPTION
        PUBSUB_ANSWER_TOPIC
        PUBSUB_ANSWER_SUBSCRIPTION
        DB_INSTANCE_NAME
        DB_NAME
        DB_USER
        DB_PASSWORD
        VITE_SENTRY_DSN
        SENTRY_SERVER_DSN
        SENTRY_WORKER_DSN
        SENTRY_CLOUD_FUNCTION_DSN
        ARTIFACT_REPOSITORY
        ASK_TIMEOUT_MS
    )

    for name in "${required[@]}"; do
        require_env "${name}"
    done

    if [[ ! -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
        echo "GOOGLE_APPLICATION_CREDENTIALS file not found: ${GOOGLE_APPLICATION_CREDENTIALS}" >&2
        exit 1
    fi
}

# Install macOS tools needed by this minimal deploy script.
install_prerequisites() {
    if ! command -v brew >/dev/null 2>&1; then
        echo "Homebrew is required. Install it first: https://brew.sh" >&2
        exit 1
    fi

    if ! command -v gcloud >/dev/null 2>&1; then
        brew install --cask google-cloud-sdk
    fi

    if ! command -v docker >/dev/null 2>&1; then
        brew install --cask docker
        echo "Start Docker Desktop and run this script again." >&2
        exit 1
    fi

    if ! command -v npm >/dev/null 2>&1; then
        brew install node
    fi

    if ! command -v cloud-sql-proxy >/dev/null 2>&1; then
        brew install cloud-sql-proxy
    fi

    if ! command -v psql >/dev/null 2>&1; then
        brew install postgresql@16
        export PATH="$(brew --prefix postgresql@16)/bin:${PATH}"
    fi
}

# Authenticate gcloud using service account JSON path from env.
authenticate_gcp() {
    gcloud auth activate-service-account --key-file="${GOOGLE_APPLICATION_CREDENTIALS}"
    gcloud config set project "${GCP_PROJECT_ID}"
}

# Enable every API needed by this new project deployment.
enable_apis() {
    gcloud services enable \
        artifactregistry.googleapis.com \
        cloudbuild.googleapis.com \
        cloudfunctions.googleapis.com \
        run.googleapis.com \
        pubsub.googleapis.com \
        storage.googleapis.com \
        sqladmin.googleapis.com \
        servicenetworking.googleapis.com \
        compute.googleapis.com \
        eventarc.googleapis.com
}

# Create Artifact Registry if it does not already exist.
ensure_artifact_registry() {
    if ! gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" --location="${GCP_REGION}" >/dev/null 2>&1; then
        gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
            --repository-format=docker \
            --location="${GCP_REGION}"
    fi

    gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet
}

# Create GCS upload bucket if it does not already exist.
ensure_bucket() {
    if ! gsutil ls -b "gs://${GCS_BUCKET}" >/dev/null 2>&1; then
        gsutil mb -l "${GCP_REGION}" "gs://${GCS_BUCKET}"
    fi
}

# Create Pub/Sub topics/subscriptions for worker jobs and worker answers.
ensure_pubsub() {
    ensure_topic "${PUBSUB_TOPIC}"
    ensure_subscription "${PUBSUB_SUBSCRIPTION}" "${PUBSUB_TOPIC}" 600
    ensure_topic "${PUBSUB_ANSWER_TOPIC}"
    ensure_subscription "${PUBSUB_ANSWER_SUBSCRIPTION}" "${PUBSUB_ANSWER_TOPIC}" 60
}

# Create one Pub/Sub topic if missing.
ensure_topic() {
    local topic="$1"

    if ! gcloud pubsub topics describe "${topic}" >/dev/null 2>&1; then
        gcloud pubsub topics create "${topic}"
    fi
}

# Create one Pub/Sub subscription if missing.
ensure_subscription() {
    local subscription="$1"
    local topic="$2"
    local ack_deadline="$3"

    if ! gcloud pubsub subscriptions describe "${subscription}" >/dev/null 2>&1; then
        gcloud pubsub subscriptions create "${subscription}" \
            --topic="${topic}" \
            --ack-deadline="${ack_deadline}"
    fi
}

# Create Cloud SQL PostgreSQL, database, and app user if missing.
ensure_database() {
    if ! gcloud sql instances describe "${DB_INSTANCE_NAME}" >/dev/null 2>&1; then
        gcloud sql instances create "${DB_INSTANCE_NAME}" \
            --database-version=POSTGRES_16 \
            --edition=ENTERPRISE \
            --tier=db-f1-micro \
            --region="${GCP_REGION}" \
            --root-password="${DB_PASSWORD}" \
            --storage-size=10GB
    fi

    if ! gcloud sql databases describe "${DB_NAME}" --instance="${DB_INSTANCE_NAME}" >/dev/null 2>&1; then
        gcloud sql databases create "${DB_NAME}" --instance="${DB_INSTANCE_NAME}"
    fi

    if ! gcloud sql users list --instance="${DB_INSTANCE_NAME}" --format='value(name)' | grep -qx "${DB_USER}"; then
        gcloud sql users create "${DB_USER}" --instance="${DB_INSTANCE_NAME}" --password="${DB_PASSWORD}"
    fi
}

# Return Cloud SQL connection name.
get_cloud_sql_connection_name() {
    gcloud sql instances describe "${DB_INSTANCE_NAME}" --format='value(connectionName)'
}

# Build Unix-socket DATABASE_URL used in Cloud Run and Cloud Functions.
build_cloud_database_url() {
    local connection_name="$1"
    echo "postgres://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${connection_name}"
}

# Start local Cloud SQL Auth Proxy for schema initialization.
start_cloud_sql_proxy() {
    local connection_name="$1"
    cloud-sql-proxy "${connection_name}" --port 5433 >/tmp/chatrag-cloud-sql-proxy.log 2>&1 &
    PROXY_PID="$!"
    sleep 3
}

# Apply PostgreSQL schema for conversations, locks, messages, and worker events.
initialize_database_schema() {
    local connection_name="$1"
    start_cloud_sql_proxy "${connection_name}"
    PGPASSWORD="${DB_PASSWORD}" psql \
        --host=127.0.0.1 \
        --port=5433 \
        --username="${DB_USER}" \
        --dbname="${DB_NAME}" \
        --file="${SCRIPT_DIR}/schema.sql"
    stop_cloud_sql_proxy
    PROXY_PID=""
}

# Build full Artifact Registry image URI.
image_uri() {
    local image_name="$1"
    echo "${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REPOSITORY}/${image_name}:latest"
}

# Build frontend + server Docker image and push it.
build_and_push_server() {
    local image
    image="$(image_uri "${SERVER_SERVICE_NAME}")"

    docker build \
        -f "${ROOT_DIR}/server/Dockerfile" \
        --build-arg VITE_APP_BASE_URL="${VITE_APP_BASE_URL}" \
        --build-arg VITE_UPLOAD_FUNCTION_URL="${VITE_UPLOAD_FUNCTION_URL}" \
        --build-arg VITE_SENTRY_DSN="${VITE_SENTRY_DSN}" \
        --build-arg VITE_SENTRY_ENVIRONMENT="${VITE_SENTRY_ENVIRONMENT}" \
        -t "${image}" \
        "${ROOT_DIR}"

    docker push "${image}"
    echo "${image}"
}

# Build Python worker image and push it.
build_and_push_worker() {
    local image
    image="$(image_uri "${WORKER_POOL_NAME}")"

    docker build -f "${ROOT_DIR}/worker/Dockerfile" -t "${image}" "${ROOT_DIR}/worker"
    docker push "${image}"
    echo "${image}"
}

# Deploy Python Cloud Run Worker Pool that pulls worker-topic messages.
deploy_worker_pool() {
    local image="$1"
    local connection_name="$2"
    local database_url="$3"

    gcloud beta run worker-pools deploy "${WORKER_POOL_NAME}" \
        --image="${image}" \
        --region="${GCP_REGION}" \
        --cpu="${WORKER_CPU}" \
        --memory="${WORKER_MEMORY}" \
        --instances="${WORKER_INSTANCES}" \
        --add-cloudsql-instances="${connection_name}" \
        --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},PUBSUB_SUBSCRIPTION=${PUBSUB_SUBSCRIPTION},PUBSUB_ANSWER_TOPIC=${PUBSUB_ANSWER_TOPIC},WORKER_STATUS=${WORKER_STATUS},DATABASE_URL=${database_url},SENTRY_DSN=${SENTRY_WORKER_DSN},SENTRY_ENVIRONMENT=${SENTRY_ENVIRONMENT},SENTRY_RELEASE=${SENTRY_RELEASE}"
}

# Deploy Node Cloud Run server that serves SPA, /api/*, SSE, and plain HTTP /ask.
deploy_server() {
    local image="$1"
    local connection_name="$2"
    local database_url="$3"

    gcloud run deploy "${SERVER_SERVICE_NAME}" \
        --image="${image}" \
        --region="${GCP_REGION}" \
        --allow-unauthenticated \
        --port=8080 \
        --cpu="${SERVER_CPU}" \
        --memory="${SERVER_MEMORY}" \
        --min-instances="${SERVER_MIN_INSTANCES}" \
        --max-instances="${SERVER_MAX_INSTANCES}" \
        --add-cloudsql-instances="${connection_name}" \
        --set-env-vars="SENTRY_DSN=${SENTRY_SERVER_DSN},SENTRY_ENVIRONMENT=${SENTRY_ENVIRONMENT},SENTRY_RELEASE=${SENTRY_RELEASE},DATABASE_URL=${database_url},PUBSUB_TOPIC=${PUBSUB_TOPIC},PUBSUB_ANSWER_SUBSCRIPTION=${PUBSUB_ANSWER_SUBSCRIPTION},ASK_TIMEOUT_MS=${ASK_TIMEOUT_MS},FRONTEND_DIST_PATH=/app/frontend/dist,ALLOWED_ORIGINS=${ALLOWED_ORIGINS},PUBLIC_APP_DOMAIN=${PUBLIC_APP_DOMAIN}"
}

# Deploy Gen2 upload Cloud Function that stores file and publishes processing job.
deploy_upload_function() {
    local connection_name="$1"
    local database_url="$2"

    pushd "${ROOT_DIR}/cloud-function" >/dev/null
    npm install

    gcloud functions deploy "${UPLOAD_FUNCTION_NAME}" \
        --gen2 \
        --runtime=nodejs22 \
        --region="${GCP_REGION}" \
        --source=. \
        --entry-point=uploadHandler \
        --trigger-http \
        --allow-unauthenticated \
        --set-cloudsql-instances="${connection_name}" \
        --set-env-vars="GCS_BUCKET=${GCS_BUCKET},PUBSUB_TOPIC=${PUBSUB_TOPIC},DATABASE_URL=${database_url},SENTRY_DSN=${SENTRY_CLOUD_FUNCTION_DSN},SENTRY_ENVIRONMENT=${SENTRY_ENVIRONMENT},SENTRY_RELEASE=${SENTRY_RELEASE},ALLOWED_ORIGINS=${ALLOWED_ORIGINS},PUBLIC_APP_DOMAIN=${PUBLIC_APP_DOMAIN}"

    popd >/dev/null
}

# Print service URLs after deployment completes.
print_summary() {
    local server_url
    local function_url
    local project_number

    server_url="$(gcloud run services describe "${SERVER_SERVICE_NAME}" --region="${GCP_REGION}" --format='value(status.url)')"
    function_url="$(gcloud functions describe "${UPLOAD_FUNCTION_NAME}" --gen2 --region="${GCP_REGION}" --format='value(serviceConfig.uri)')"
    project_number="$(get_project_number)"

    echo ""
    echo "Deployed ChatRAG (${ENVIRONMENT_NAME}) - Option A"
    echo "Server URL:     ${server_url}"
    echo "Upload URL:     ${function_url}"
    echo "Future domain:  ${PUBLIC_APP_DOMAIN} (not mapped by this script)"
    echo "Worker pool:    ${WORKER_POOL_NAME}"
    echo "Worker bus:     ${PUBSUB_TOPIC} -> ${PUBSUB_SUBSCRIPTION}"
    echo "Answer bus:     ${PUBSUB_ANSWER_TOPIC} -> ${PUBSUB_ANSWER_SUBSCRIPTION}"
    echo "Cloud Run hint: https://${SERVER_SERVICE_NAME}-${project_number}.${GCP_REGION}.run.app"
}

# Run full deployment flow.
main() {
    trap stop_cloud_sql_proxy EXIT

    load_env
    install_prerequisites
    authenticate_gcp
    enable_apis
    derive_frontend_envs
    require_all_envs
    ensure_artifact_registry
    ensure_bucket
    ensure_pubsub
    ensure_database

    local connection_name
    local database_url
    local server_image
    local worker_image

    connection_name="$(get_cloud_sql_connection_name)"
    database_url="$(build_cloud_database_url "${connection_name}")"
    initialize_database_schema "${connection_name}"
    server_image="$(build_and_push_server)"
    worker_image="$(build_and_push_worker)"

    deploy_worker_pool "${worker_image}" "${connection_name}" "${database_url}"
    deploy_server "${server_image}" "${connection_name}" "${database_url}"
    deploy_upload_function "${connection_name}" "${database_url}"
    print_summary
}

main "$@"
