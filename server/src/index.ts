import { createApp } from "./app.js"
import { createPendingAskRegistry, resolvePendingAnswer } from "./ask.js"
import { createConfig } from "./config.js"
import { createDatabasePool, insertConversationMetadata } from "./db.js"
import { createPubSubClient, startAnswerSubscriber } from "./pubsub.js"
import { broadcastAnswer, createSseRegistry } from "./sse.js"
import { captureDebugMessage, captureException, initSentry } from "./sentry.js"

const config = createConfig()
const pubsub = createPubSubClient()
const pool = createDatabasePool(config)
const pending = createPendingAskRegistry()
const sseRegistry = createSseRegistry()

initSentry(config)

startAnswerSubscriber(pubsub, config, async (payload) => {
    await insertConversationMetadata(pool, {
        uid: payload.uid || "home",
        traceId: payload.traceId,
        fingerprint: payload.fingerprint,
        source: "server",
        eventType: "pubsub_answer_topic_received",
        topicName: config.answerSubscription,
        direction: "in",
        payload,
        message: "server received worker answer from answer subscription"
    })

    const resolved = resolvePendingAnswer(pending, payload)
    broadcastAnswer(sseRegistry, payload)
    captureDebugMessage("server received worker answer", { payload, resolved })
})

const app = createApp(config, pubsub, pool, sseRegistry, pending)

app.listen(config.port, () => {
    captureDebugMessage("server started", { port: config.port })
    console.log(`chatrag-server listening on ${config.port}`)
})

process.on("unhandledRejection", captureException)
process.on("uncaughtException", captureException)
