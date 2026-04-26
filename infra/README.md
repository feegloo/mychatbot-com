# Infra

Bash-based multi-env deployment for macOS.

## Diagram: Infra deploy flow

```mermaid
flowchart TD
    Deploy["deploy-gcp.sh"]
    EnvProd["infra .env.prod"]
    EnvDev["infra .env.dev"]
    APIs["Enable GCP APIs"]
    Registry["Artifact Registry"]
    Bucket["Cloud Storage bucket"]
    PubSub["Pub/Sub topics and subscriptions"]
    Database["Cloud SQL PostgreSQL"]
    Schema["schema.sql"]
    Server["Cloud Run server"]
    Worker["Cloud Run Worker Pool"]
    Function["Cloud Function upload"]

    Deploy --> EnvProd
    Deploy --> EnvDev
    Deploy --> APIs
    Deploy --> Registry
    Deploy --> Bucket
    Deploy --> PubSub
    Deploy --> Database
    Database --> Schema
    Deploy --> Server
    Deploy --> Worker
    Deploy --> Function
    Function -->|"inject SERVER_HEALTH_URL"| Server
```

## Diagram: GCP resources

```mermaid
flowchart LR
    Project["GCP project chatrag-app"]
    Run["Cloud Run chatrag-server"]
    WorkerPool["Worker Pool chatrag-worker"]
    Function["Function chatrag-upload"]
    Sql["Cloud SQL chatrag-db"]
    Topic1["Topic chatrag-worker-topic"]
    Topic2["Topic chatrag-answer-topic"]
    Bucket["GCS chatrag-app-storage"]

    Project --> Run
    Project --> WorkerPool
    Project --> Function
    Project --> Sql
    Project --> Topic1
    Project --> Topic2
    Project --> Bucket
```


## Diagram: CI/CD workflow

```mermaid
flowchart TD
    Push2Branch["Push to branch 2.0"]
    BuildWorkflow["GitHub Actions build.yml"]
    DeployWorkflow["GitHub Actions deploy.yml"]
    Secrets["GitHub Secrets"]
    EnvFile["Generate infra env file"]
    ServiceAccount["Activate service account"]
    DeployScript["Run infra gcp deploy script"]
    GcpResources["Cloud Run, Function, Worker Pool, Pub/Sub, SQL"]

    Push2Branch --> BuildWorkflow
    Push2Branch --> DeployWorkflow
    Secrets --> EnvFile
    Secrets --> ServiceAccount
    EnvFile --> DeployScript
    ServiceAccount --> DeployScript
    DeployScript --> GcpResources
```

## Performance notes

- Dockerfiles use BuildKit cache mounts for npm and pip downloads.
- Runtime images are slim Node/Python images with build dependencies left in intermediate stages.
- Cloud Run server uses min instances from env; set `SERVER_MIN_INSTANCES=0` for cheapest idle behavior.
- Worker Pool can be paused by setting `WORKER_INSTANCES=0`.

## Env files

`infra/.env.dev` and `infra/.env.prod` are committed templates with non-secret defaults and empty secret placeholders.

For local deploys, copy one of the examples and fill secrets:

```bash
cp infra/.env.prod.local.example infra/.env.prod.local
cp infra/.env.dev.local.example infra/.env.dev.local
```

`gcp-deploy.sh` loads the base env first, then overlays `.local` values when the file exists.

GitHub Actions does the same thing: it keeps the committed env file and creates only a small `.env.<env>.local` file from GitHub Secrets.

## Cloud Run SSE prewarm

The SSE/HTTP server is deployed with `SERVER_MIN_INSTANCES=0` and `SERVER_REQUEST_TIMEOUT_SECONDS=3600`.
This minimizes idle cost while still allowing long-lived SSE requests.

After frontend upload calls the Cloud Function, the function calls `GET /health` on the Cloud Run server through `SERVER_HEALTH_URL`.
The deploy script injects the real URL after the server is deployed:

```text
https://<cloud-run-server-url>/health
```

This prewarms the server before the browser navigates to `/c/:uid` or opens an SSE connection.
