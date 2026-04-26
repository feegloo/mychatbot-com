# ChatRAG - GCP Option A multi-env

This repository is a small production-shaped ChatRAG skeleton for the new GCP project `chatrag-app`.

Option A means:

- `chatrag.app` stays mapped to the old GCP project for now.
- this new project uses generated GCP URLs:
  - Cloud Run server: `https://<service>-<project-number>.<region>.run.app`
  - Cloud Function upload: `https://<region>-<project-id>.cloudfunctions.net/<function>`
  - Cloud Run Worker Pool: no public HTTP URL
- later, after detaching the old project, map `chatrag.app` to the new Cloud Run server.

## Structure

```text
frontend/        Vite + Vue 3 + TypeScript app
server/          TypeScript Node/Express server, SPA hosting, SSE, /ask
cloud-function/  upload function: file -> GCS -> DB -> Pub/Sub
worker/          Python Pub/Sub worker with PostgreSQL locks and answer publishing
infra/           dev/prod envs, schema, deploy script
docs/            extra architecture notes
```

## Local frontend dev

```bash
cd frontend
npm install
npm run dev
```

Vite serves `frontend/index.html` on `http://localhost:5173`.

## Deploy prod by default

```bash
./infra/deploy-gcp.sh
```

## Deploy dev explicitly

```bash
ENV=dev ./infra/deploy-gcp.sh
```

## Root Diagram: High-level system flow

```mermaid
flowchart LR
    User["User Browser"]
    Frontend["frontend: Vite Vue App"]
    UploadFunction["cloud-function: chatrag-upload"]
    Server["server: chatrag-server Cloud Run"]
    Storage["GCS: upload bucket"]
    Database["Cloud SQL PostgreSQL"]
    WorkerTopic["Pub/Sub: chatrag-worker-topic"]
    Worker["worker: chatrag-worker pool"]
    AnswerTopic["Pub/Sub: chatrag-answer-topic"]

    User -->|"open app"| Frontend
    Frontend -->|"POST upload function URL"| UploadFunction
    UploadFunction -->|"write PDF"| Storage
    UploadFunction -->|"INSERT conversations and metadata"| Database
    UploadFunction -->|"GET /health prewarm"| Server
    UploadFunction -->|"publish process_pdf"| WorkerTopic
    WorkerTopic -->|"pull message"| Worker
    Worker -->|"lock and write messages metadata"| Database
    Frontend -->|"POST /ask"| Server
    Server -->|"publish ask"| WorkerTopic
    Worker -->|"publish answer"| AnswerTopic
    AnswerTopic -->|"pull answer"| Server
    Server -->|"HTTP /ask response and SSE answer"| Frontend
```

## Root Diagram: Detailed event and metadata flow

```mermaid
flowchart TD
    Start["Browser loads home page"]
    Fingerprint["Create fingerprint in Local Storage"]
    SseOpen["Open EventSource to server"]
    SseMeta["Insert conversations_metadatas: sse_connected"]
    AskSubmit["User submits chat input"]
    AskHttp["Server receives POST ask"]
    AskMeta["Insert conversations_metadatas: ask_received"]
    PublishAsk["Publish ask message to worker topic"]
    PublishAskMeta["Insert conversations_metadatas: pubsub_worker_topic_published"]
    WorkerPull["Worker pulls message from worker subscription"]
    WorkerPullMeta["Insert conversations_metadatas: pubsub_message_received"]
    Idempotency["Insert conversation_messages by unique trace_id"]
    DuplicateCheck["Only first worker continues"]
    ProcessAsk["Worker creates answer string"]
    StoreAnswer["Update conversation_messages with answer"]
    PublishAnswer["Publish answer to answer topic"]
    PublishAnswerMeta["Insert conversations_metadatas: answer_topic_published"]
    ServerAnswer["Server pulls answer subscription"]
    ServerAnswerMeta["Insert conversations_metadatas: pubsub_answer_topic_received"]
    ResolveHttp["Resolve pending POST ask request within 20 seconds"]
    ResponseMeta["Insert conversations_metadatas: ask_response_returned"]
    BrowserAnswer["Browser renders assistant message"]

    Start --> Fingerprint
    Fingerprint --> SseOpen
    SseOpen --> SseMeta
    Fingerprint --> AskSubmit
    AskSubmit -->|"POST /ask with traceId and fingerprint"| AskHttp
    AskHttp --> AskMeta
    AskMeta --> PublishAsk
    PublishAsk --> PublishAskMeta
    PublishAsk -->|"topic: chatrag-worker-topic"| WorkerPull
    WorkerPull --> WorkerPullMeta
    WorkerPullMeta --> Idempotency
    Idempotency --> DuplicateCheck
    DuplicateCheck --> ProcessAsk
    ProcessAsk --> StoreAnswer
    StoreAnswer --> PublishAnswer
    PublishAnswer --> PublishAnswerMeta
    PublishAnswer -->|"topic: chatrag-answer-topic"| ServerAnswer
    ServerAnswer --> ServerAnswerMeta
    ServerAnswerMeta --> ResolveHttp
    ResolveHttp --> ResponseMeta
    ResolveHttp --> BrowserAnswer
```

## Root Diagram: Upload PDF flow

```mermaid
flowchart TD
    BrowserUpload["Browser selects PDF"]
    UploadPost["Cloud Function receives multipart upload"]
    StoreFile["Store file in Cloud Storage"]
    CreateConversation["Insert conversations row"]
    UploadMetadata["Insert conversations_metadatas upload_received"]
    PrewarmServer["Call server health endpoint"]
    PublishPdf["Publish process_pdf message"]
    WorkerPdf["Worker pulls process_pdf"]
    LockPdf["Insert processing_locks row"]
    ProcessPdf["Run Python PDF processor"]
    DonePdf["Update conversation status processed"]
    DebugMetadata["Insert conversations_metadatas for each step"]

    BrowserUpload -->|"POST upload function URL"| UploadPost
    UploadPost --> StoreFile
    UploadPost --> CreateConversation
    CreateConversation --> UploadMetadata
    UploadMetadata --> PrewarmServer
    PrewarmServer -->|"GET /health"| DonePrewarm["Cloud Run server wakes if scaled to zero"]
    UploadMetadata --> PublishPdf
    PublishPdf -->|"topic: chatrag-worker-topic"| WorkerPdf
    WorkerPdf --> LockPdf
    LockPdf --> ProcessPdf
    ProcessPdf --> DonePdf
    WorkerPdf --> DebugMetadata
```

## Multi-env naming

`infra/.env.dev` uses names like:

- `chatrag-dev-server`
- `chatrag-dev-upload`
- `chatrag-dev-worker`
- `chatrag-dev-worker-topic`

`infra/.env.prod` uses final names like:

- `chatrag-server`
- `chatrag-upload`
- `chatrag-worker`
- `chatrag-worker-topic`

## Domain migration later

This ZIP does not map `chatrag.app`.

When you are ready to replace the old project:

1. delete old Cloud Run domain mapping for `chatrag.app`
2. verify the domain in the new project if needed
3. create Cloud Run domain mapping for `chatrag-server`
4. update DNS at registrar
5. set `VITE_APP_BASE_URL=https://chatrag.app` in `infra/.env.prod`
6. redeploy `./infra/deploy-gcp.sh`

## GitHub Actions

This repository includes two workflows:

- `.github/workflows/build.yml` - builds and checks frontend, server, cloud-function, and worker.
- `.github/workflows/deploy.yml` - deploys to GCP on push to branch `2.0` and can also be started manually.

Required GitHub Secrets for deploy:

```text
GCP_SERVICE_ACCOUNT_KEY
```

Optional GitHub Secrets used to create `infra/.env.prod.local` or `infra/.env.dev.local` during CI deploy:

```text
DB_PASSWORD
VITE_SENTRY_DSN
SENTRY_SERVER_DSN
SENTRY_WORKER_DSN
SENTRY_CLOUD_FUNCTION_DSN
SENTRY_AUTH_TOKEN
```

The committed `infra/.env.prod` and `infra/.env.dev` files contain non-secret defaults and empty secret placeholders. Locally, put real secrets into `infra/.env.prod.local` or `infra/.env.dev.local`; those files are ignored by git.
