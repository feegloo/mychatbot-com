#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENVIRONMENT_NAME="${ENV:-prod}"
ENV_FILE="${SCRIPT_DIR}/.env.${ENVIRONMENT_NAME}"
PROXY_PID=""
GENERATED_DB_PASSWORD="false"
export DOCKER_BUILDKIT=1
CI_MODE="${CI:-false}"

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

# Load env vars for selected environment and optional local secret overrides.
#
# Committed template: infra/.env.dev or infra/.env.prod
# Local secrets:      infra/.env.dev.local or infra/.env.prod.local
#
# GitHub Actions can either:
# - provide GOOGLE_APPLICATION_CREDENTIALS through the workflow, and
# - append a tiny infra/.env.prod.local file from a few secrets.
load_env() {
    local local_env_file="${ENV_FILE}.local"

    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Missing env file: ${ENV_FILE}" >&2
        echo "Use ENV=dev or ENV=prod." >&2
        exit 1
    fi

    set -a
    source "${ENV_FILE}"

    if [[ -f "${local_env_file}" ]]; then
        source "${local_env_file}"
    fi

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
        ARTIFACT_REPOSITORY
        ASK_TIMEOUT_MS
    )

    for name in "${required[@]}"; do
        require_env "${name}"
    done

    warn_optional_env VITE_SENTRY_DSN
    warn_optional_env SENTRY_SERVER_DSN
    warn_optional_env SENTRY_WORKER_DSN
    warn_optional_env SENTRY_CLOUD_FUNCTION_DSN
}

# Print a warning for optional env vars that improve production observability.
warn_optional_env() {
    local name="$1"
    local value="${!name:-}"

    if [[ -z "${value}" ]]; then
        log "Optional env ${name} is empty; deploy will continue without this integration."
    fi
}

# Install tools needed by this deploy script.
#
# Local macOS mode installs missing tools with Homebrew.
# GitHub Actions / CI mode only verifies commands because the workflow installs them.
install_prerequisites() {
    if [[ "${CI_MODE}" == "true" ]]; then
        require_command gcloud
        require_command gsutil
        require_command docker
        require_command npm
        require_command cloud-sql-proxy
        require_command psql
        return
    fi

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

# Fail fast when a command expected by CI is missing.
require_command() {
    local name="$1"

    if ! command -v "${name}" >/dev/null 2>&1; then
        echo "Missing required command: ${name}" >&2
        exit 1
    fi
}

# Authenticate Google Cloud SDK.
#
# Local mode uses browser login (`gcloud auth login`) like the old deploy script.
# CI mode uses GOOGLE_APPLICATION_CREDENTIALS generated from a GitHub secret.
authenticate_gcp() {
    if [[ "${CI_MODE}" == "true" ]]; then
        require_env GOOGLE_APPLICATION_CREDENTIALS

        if [[ ! -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
            echo "GOOGLE_APPLICATION_CREDENTIALS file not found: ${GOOGLE_APPLICATION_CREDENTIALS}" >&2
            exit 1
        fi

        gcloud auth activate-service-account --key-file="${GOOGLE_APPLICATION_CREDENTIALS}"
        gcloud config set project "${GCP_PROJECT_ID}"
        return
    fi

    local active_account

    active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"

    if [[ -z "${active_account}" ]]; then
        log "No active Cloud SDK account found. Opening browser login..."
        gcloud auth login
    else
        log "Using active Cloud SDK account: ${active_account}"
    fi

    gcloud config set project "${GCP_PROJECT_ID}"

    if ! gcloud auth print-access-token >/dev/null 2>&1; then
        log "Cloud SDK token unavailable. Opening browser login..."
        gcloud auth login
    fi

    if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
        log "Application Default Credentials missing. Opening ADC browser login..."
        gcloud auth application-default login
    fi
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

# Return 0 when the configured Cloud SQL instance already exists.
cloud_sql_instance_exists() {
    gcloud sql instances describe "${DB_INSTANCE_NAME}" >/dev/null 2>&1
}

# Generate a strong random database password for first-time deployments.
generate_db_password() {
    openssl rand -base64 32 | tr -d '\n'
}

# Print a visible warning with the generated DB password. Save it into the env file
# after the first deploy, because future deploys will require DB_PASSWORD from env.
print_generated_db_password() {
    echo ""
    echo "============================================================"
    echo "  Cloud SQL was created during this deploy."
    echo "  Save this password into ${ENV_FILE}:"
    echo ""
    echo "  DB_PASSWORD=${DB_PASSWORD}"
    echo ""
    echo "  Keep it private. The next deploy will read DB_PASSWORD from env."
    echo "============================================================"
    echo ""
}

# Resolve DB_PASSWORD according to deployment mode.
#
# First deploy: when the Cloud SQL instance does not exist, generate a password.
# Later deploys: when the instance already exists, require DB_PASSWORD from env so
# the script does not accidentally rotate or guess the existing database password.
resolve_database_password() {
    if cloud_sql_instance_exists; then
        if [[ -z "${DB_PASSWORD:-}" ]]; then
            echo "Cloud SQL instance '${DB_INSTANCE_NAME}' already exists." >&2
            echo "Set DB_PASSWORD in ${ENV_FILE} before deploying again." >&2
            exit 1
        fi

        log "Cloud SQL instance exists. Using DB_PASSWORD from env."
        return
    fi

    if [[ -z "${DB_PASSWORD:-}" ]]; then
        DB_PASSWORD="$(generate_db_password)"
        export DB_PASSWORD
        GENERATED_DB_PASSWORD="true"
    else
        GENERATED_DB_PASSWORD="false"
    fi
}

# Create Cloud SQL PostgreSQL, database, and app user if missing.
ensure_database() {
    resolve_database_password

    if ! cloud_sql_instance_exists; then
        log "Creating Cloud SQL PostgreSQL instance: ${DB_INSTANCE_NAME}"
        gcloud sql instances create "${DB_INSTANCE_NAME}" \
            --database-version=POSTGRES_16 \
            --edition=ENTERPRISE \
            --tier=db-f1-micro \
            --region="${GCP_REGION}" \
            --root-password="${DB_PASSWORD}" \
            --storage-size=10GB
    fi

    if ! gcloud sql databases describe "${DB_NAME}" --instance="${DB_INSTANCE_NAME}" >/dev/null 2>&1; then
        log "Creating database: ${DB_NAME}"
        gcloud sql databases create "${DB_NAME}" --instance="${DB_INSTANCE_NAME}"
    fi

    if ! gcloud sql users list --instance="${DB_INSTANCE_NAME}" --format='value(name)' | grep -qx "${DB_USER}"; then
        log "Creating database user: ${DB_USER}"
        gcloud sql users create "${DB_USER}" --instance="${DB_INSTANCE_NAME}" --password="${DB_PASSWORD}"
    fi

    if [[ "${GENERATED_DB_PASSWORD:-false}" == "true" ]]; then
        print_generated_db_password
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

# Apply PostgreSQL schema from infra/schema.sql.
initialize_database_schema() {
    local connection_name="$1"
    local schema_file="${SCRIPT_DIR}/schema.sql"

    if [[ ! -f "${schema_file}" ]]; then
        echo "Missing schema file: ${schema_file}" >&2
        exit 1
    fi

    log "Initializing database schema from ${schema_file}"
    start_cloud_sql_proxy "${connection_name}"
    PGPASSWORD="${DB_PASSWORD}" psql \
        --host=127.0.0.1 \
        --port=5433 \
        --username="${DB_USER}" \
        --dbname="${DB_NAME}" \
        --file="${schema_file}"
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

# Return the configured server min instances, defaulting to 0.
#
# Cloud Run HTTP services wake up automatically on the next incoming request when
# min instances is 0. This is the cheapest mode for the SSE server because the
# container is allowed to scale down to zero after a period without traffic.
#
# Note: Cloud Run does not expose an exact "stop after 1h idle" knob. The nearest
# production setting is min-instances=0, which lets Cloud Run scale the service
# down after inactivity and cold-start it again on the next request.
server_min_instances() {
    echo "${SERVER_MIN_INSTANCES:-0}"
}

# Return the configured Cloud Run request timeout, defaulting to 3600 seconds.
#
# This does not control idle scale-down. It only allows long-lived HTTP/SSE
# requests to stay open for up to 1 hour.
server_request_timeout_seconds() {
    echo "${SERVER_REQUEST_TIMEOUT_SECONDS:-3600}"
}

# Deploy Node Cloud Run server that serves SPA, /api/*, SSE, and plain HTTP /ask.
#
# Cost behavior:
# - --min-instances=0 allows the HTTP/SSE server to stop when there is no traffic.
# - The first new request wakes the container automatically.
# - --timeout=3600 allows a long SSE request to stay open for up to 1 hour.
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
        --min-instances="$(server_min_instances)" \
        --max-instances="${SERVER_MAX_INSTANCES}" \
        --timeout="$(server_request_timeout_seconds)" \
        --cpu-boost \
        --add-cloudsql-instances="${connection_name}" \
        --set-env-vars="SENTRY_DSN=${SENTRY_SERVER_DSN},SENTRY_ENVIRONMENT=${SENTRY_ENVIRONMENT},SENTRY_RELEASE=${SENTRY_RELEASE},DATABASE_URL=${database_url},PUBSUB_TOPIC=${PUBSUB_TOPIC},PUBSUB_ANSWER_SUBSCRIPTION=${PUBSUB_ANSWER_SUBSCRIPTION},ASK_TIMEOUT_MS=${ASK_TIMEOUT_MS},FRONTEND_DIST_PATH=/app/frontend/dist,ALLOWED_ORIGINS=${ALLOWED_ORIGINS},PUBLIC_APP_DOMAIN=${PUBLIC_APP_DOMAIN}"
}

# Deploy Gen2 upload Cloud Function that stores file, publishes processing job, and prewarms server.
deploy_upload_function() {
    local connection_name="$1"
    local database_url="$2"
    local server_health_url="$3"

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
        --set-env-vars="GCS_BUCKET=${GCS_BUCKET},PUBSUB_TOPIC=${PUBSUB_TOPIC},DATABASE_URL=${database_url},SENTRY_DSN=${SENTRY_CLOUD_FUNCTION_DSN},SENTRY_ENVIRONMENT=${SENTRY_ENVIRONMENT},SENTRY_RELEASE=${SENTRY_RELEASE},ALLOWED_ORIGINS=${ALLOWED_ORIGINS},PUBLIC_APP_DOMAIN=${PUBLIC_APP_DOMAIN},SERVER_HEALTH_URL=${server_health_url},PREWARM_SERVER_TIMEOUT_MS=${PREWARM_SERVER_TIMEOUT_MS:-8000}"

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
    echo "Server scaling: min-instances=$(server_min_instances), timeout=$(server_request_timeout_seconds)s"
    echo "Server prewarm:  upload function calls ${SERVER_HEALTH_URL:-${server_url}/health}"
    echo "Idle behavior:  Cloud Run may scale server to 0 when idle; next request wakes it."
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
    local server_url

    connection_name="$(get_cloud_sql_connection_name)"
    database_url="$(build_cloud_database_url "${connection_name}")"
    initialize_database_schema "${connection_name}"
    server_image="$(build_and_push_server)"
    worker_image="$(build_and_push_worker)"

    deploy_worker_pool "${worker_image}" "${connection_name}" "${database_url}"
    deploy_server "${server_image}" "${connection_name}" "${database_url}"
    server_url="$(gcloud run services describe "${SERVER_SERVICE_NAME}" --region="${GCP_REGION}" --format='value(status.url)')"
    deploy_upload_function "${connection_name}" "${database_url}" "${SERVER_HEALTH_URL:-${server_url}/health}"
    print_summary
}

main "$@"
