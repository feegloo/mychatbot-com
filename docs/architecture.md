# Architecture

## Diagram: Option A runtime architecture

```mermaid
flowchart TD
    Browser["Browser on chatrag.app or generated URL"]
    Frontend["Vite Vue frontend"]
    UploadFunction["Cloud Function chatrag-upload"]
    Server["Cloud Run chatrag-server"]
    WorkerTopic["Pub/Sub chatrag-worker-topic"]
    WorkerSub["Subscription chatrag-worker-sub"]
    Worker["Cloud Run Worker Pool chatrag-worker"]
    AnswerTopic["Pub/Sub chatrag-answer-topic"]
    AnswerSub["Subscription chatrag-answer-sub"]
    Database["Cloud SQL PostgreSQL"]
    Storage["Cloud Storage"]

    Browser --> Frontend
    Frontend -->|"upload PDF"| UploadFunction
    UploadFunction --> Storage
    UploadFunction --> Database
    UploadFunction --> WorkerTopic
    WorkerTopic --> WorkerSub
    WorkerSub --> Worker
    Frontend -->|"POST /ask"| Server
    Server --> WorkerTopic
    Worker --> Database
    Worker --> AnswerTopic
    AnswerTopic --> AnswerSub
    AnswerSub --> Server
    Server --> Frontend
```

## Diagram: Metadata debug trail

```mermaid
flowchart TD
    Upload["upload_received"]
    Ask["ask_received"]
    PublishWorker["pubsub_worker_topic_published"]
    WorkerReceive["pubsub_message_received"]
    Lock["pdf_lock_acquired or ask_message_inserted"]
    AnswerPublish["answer_topic_published"]
    ServerAnswer["pubsub_answer_topic_received"]
    Response["ask_response_returned"]
    Metadata["conversations_metadatas"]

    Upload --> Metadata
    Ask --> Metadata
    PublishWorker --> Metadata
    WorkerReceive --> Metadata
    Lock --> Metadata
    AnswerPublish --> Metadata
    ServerAnswer --> Metadata
    Response --> Metadata
```

## Why max server instances is 1

The basic `/ask` implementation stores pending requests in memory while waiting up to `ASK_TIMEOUT_MS` for the answer Pub/Sub message. Keep `SERVER_MAX_INSTANCES=1` for this architecture.

For multi-instance production, move pending request correlation to Redis/Memorystore, Firestore, Cloud SQL polling, or a WebSocket/SSE fanout service.
