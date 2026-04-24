import dotenv from 'dotenv'
import path from 'node:path'

dotenv.config()

function resolvePath(value: string) {
  return path.resolve(process.cwd(), value)
}

export const config = {
  port: Number(process.env.PORT || 3000),
  publicBaseUrl: process.env.PUBLIC_BASE_URL || 'http://localhost:3000',
  databaseUrl: process.env.DATABASE_URL || 'postgres://chatrag:chatrag@localhost:5432/chatrag',
  storageProvider: process.env.STORAGE_PROVIDER || 'disk',
  storageRoot: resolvePath(process.env.STORAGE_ROOT || '../storage'),
  pythonBin: process.env.PYTHON_BIN || 'python3',
  pythonProjectRoot: resolvePath(process.env.PYTHON_PROJECT_ROOT || '../python'),
  frontendDistPath: process.env.FRONTEND_DIST_PATH
    ? resolvePath(process.env.FRONTEND_DIST_PATH)
    : '',
  chromaMode: process.env.CHROMA_MODE || 'local',
  chromaHttpHost: process.env.CHROMA_HTTP_HOST || 'http://localhost:8000',
  chromaPersistDir: resolvePath(process.env.CHROMA_PERSIST_DIR || '../data/chroma'),
  chromaApiKey: process.env.CHROMA_API_KEY || '',
  chromaTenant: process.env.CHROMA_TENANT || '',
  chromaDatabase: process.env.CHROMA_DATABASE || '',
  openAiApiKey: process.env.OPENAI_API_KEY || '',
  openAiChatModel: process.env.OPENAI_CHAT_MODEL || 'gpt-5.4-mini',
  openAiEmbeddingModel: process.env.OPENAI_EMBEDDING_MODEL || 'text-embedding-3-small',
  pythonServerUrl: process.env.PYTHON_SERVER_URL || 'http://localhost:8321',
  gcsBucket: process.env.GCS_BUCKET || '',
  logsRoot: resolvePath(process.env.LOGS_ROOT || '../logs'),
  debugUser: process.env.DEBUG_USER || 'chatrag',
  debugPass: process.env.DEBUG_PASS || 'chatragadmin',
  stripeSecretKey: process.env.STRIPE_SECRET_KEY || '',
  stripeWebhookSecret: process.env.STRIPE_WEBHOOK_SECRET || '',
  // Indexing backend: 'inline' (default) runs indexing inside the upload
  // request on the backend instance (works for local dev + single-node);
  // 'cloud_run' publishes a job to GCP Pub/Sub topic ``pubsubTopic`` so
  // the chatrag-worker Cloud Run Worker Pool can pull and process it.
  // Backend instances then LISTEN on indexing_events to relay worker
  // progress to browsers via SSE.
  workerMode: (process.env.WORKER_MODE || 'inline') as 'inline' | 'cloud_run',
  // GCP Pub/Sub topic for indexing jobs. When unset, ``cloud_run`` mode
  // falls back to inline processing (the publish helper throws and the
  // upload route logs + degrades gracefully).
  pubsubTopic: process.env.PUBSUB_TOPIC || 'chatrag-indexing',
  gcpProjectId: process.env.GCP_PROJECT_ID || process.env.GOOGLE_CLOUD_PROJECT || '',
  // Per-instance Postgres pool size. Kept small because Cloud SQL
  // db-f1-micro only allows ~25 concurrent connections total and several
  // Cloud Run instances share that budget.
  dbPoolMax: Number(process.env.DB_POOL_MAX || 3),
  dbIdleTimeoutMs: Number(process.env.DB_IDLE_TIMEOUT_MS || 10_000),
  dbConnectionTimeoutMs: Number(process.env.DB_CONNECTION_TIMEOUT_MS || 5_000),
}
