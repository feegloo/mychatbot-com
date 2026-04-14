import dotenv from "dotenv";
import path from "node:path";

dotenv.config();

function resolvePath(value: string) {
  return path.resolve(process.cwd(), value);
}

export const config = {
  port: Number(process.env.PORT || 3000),
  publicBaseUrl: process.env.PUBLIC_BASE_URL || "http://localhost:3000",
  databaseUrl: process.env.DATABASE_URL || "postgres://chatrag:chatrag@localhost:5432/chatrag",
  storageProvider: process.env.STORAGE_PROVIDER || "disk",
  storageRoot: resolvePath(process.env.STORAGE_ROOT || "../storage"),
  pythonBin: process.env.PYTHON_BIN || "python3",
  pythonProjectRoot: resolvePath(process.env.PYTHON_PROJECT_ROOT || "../python"),
  pythonIndexingMode: process.env.PYTHON_INDEXING_MODE || "script",
  frontendDistPath: process.env.FRONTEND_DIST_PATH ? resolvePath(process.env.FRONTEND_DIST_PATH) : "",
  chromaMode: process.env.CHROMA_MODE || "local",
  chromaHttpHost: process.env.CHROMA_HTTP_HOST || "http://localhost:8000",
  chromaPersistDir: resolvePath(process.env.CHROMA_PERSIST_DIR || "../data/chroma"),
  chromaApiKey: process.env.CHROMA_API_KEY || "",
  chromaTenant: process.env.CHROMA_TENANT || "",
  chromaDatabase: process.env.CHROMA_DATABASE || "",
  openAiApiKey: process.env.OPENAI_API_KEY || "",
  openAiChatModel: process.env.OPENAI_CHAT_MODEL || "gpt-5.4-mini",
  openAiEmbeddingModel: process.env.OPENAI_EMBEDDING_MODEL || "text-embedding-3-small",
  pythonServerUrl: process.env.PYTHON_SERVER_URL || "http://localhost:8321",  gcsBucket: process.env.GCS_BUCKET || "",
  // add this
  logsRoot: resolvePath(process.env.LOGS_ROOT || "../logs")
};