import { PubSub, type Message } from "@google-cloud/pubsub"
import type { AskTopicMessage, ServerConfig, WorkerAnswerPayload } from "./types.js"

export type AnswerHandler = (payload: WorkerAnswerPayload) => void | Promise<void>

/**
 * Creates Google Cloud Pub/Sub client.
 */
export function createPubSubClient(): PubSub {
    return new PubSub()
}

/**
 * Publishes ask message to worker topic.
 */
export async function publishAskMessage(pubsub: PubSub, config: ServerConfig, message: AskTopicMessage): Promise<void> {
    await pubsub.topic(config.workerTopic).publishMessage({
        json: message
    })
}

/**
 * Starts subscriber for answer topic subscription.
 */
export function startAnswerSubscriber(pubsub: PubSub, config: ServerConfig, handler: AnswerHandler): void {
    const subscription = pubsub.subscription(config.answerSubscription)

    subscription.on("message", async (message: Message) => {
        try {
            const payload = decodeAnswerMessage(message)
            await handler(payload)
            message.ack()
        } catch (error) {
            message.nack()
            throw error
        }
    })
}

/**
 * Decodes Pub/Sub answer message as JSON.
 */
function decodeAnswerMessage(message: Message): WorkerAnswerPayload {
    return JSON.parse(message.data.toString("utf8")) as WorkerAnswerPayload
}
