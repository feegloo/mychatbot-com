import { ref } from "vue"
import { createTraceId } from "../lib/fingerprint"
import { captureFrontendDebug } from "../lib/sentry"

/**
 * Creates EventSource state and opener for server-sent events stream.
 */
export function useSse(fingerprint: string) {
	const events = ref<string[]>([])
	let source: EventSource | null = null

	function append(label: string, payload: unknown): void {
		const serialized = typeof payload === "string" ? payload : JSON.stringify(payload)
		events.value.push(`${label}: ${serialized}`)
	}

	function open(uid: string): void {
		const traceId = createTraceId()
		const streamUid = uid || "home"

		source?.close()

		const endpoint = new URL(`/api/events/${encodeURIComponent(streamUid)}`, window.location.origin)
		endpoint.searchParams.set("traceId", traceId)
		endpoint.searchParams.set("fingerprint", fingerprint)

		source = new EventSource(endpoint.toString())
		captureFrontendDebug("frontend sse open", { uid: streamUid, traceId, fingerprint })

		source.addEventListener("connected", (event) => {
			append("connected", (event as MessageEvent).data)
		})

		source.addEventListener("heartbeat", (event) => {
			append("heartbeat", (event as MessageEvent).data)
		})

		source.addEventListener("answer", (event) => {
			append("answer", (event as MessageEvent).data)
		})

		source.onerror = () => {
			append("error", "SSE connection error")
			captureFrontendDebug("frontend sse error", { uid: streamUid, traceId, fingerprint })
		}
	}

	return {
		events,
		open
	}
}
