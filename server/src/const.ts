import path from "node:path"
import { fileURLToPath } from "node:url"

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

export const DEFAULT_PORT = 8080
export const DEFAULT_ASK_TIMEOUT_MS = 20_000
export const DEFAULT_WORKER_TOPIC = "chatrag-worker-topic"
export const DEFAULT_ANSWER_SUBSCRIPTION = "chatrag-answer-sub"
export const DEFAULT_PUBLIC_APP_DOMAIN = "https://chatrag.app"
export const DEFAULT_FRONTEND_DIST_PATH = path.resolve(dirname, "../../frontend/dist")
export const SERVICE_NAME = "chatrag-server"
