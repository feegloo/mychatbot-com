/**
 * OpenTelemetry setup for Node.js backend.
 *
 * Must be imported FIRST (before Sentry, Koa, etc.) so auto-instrumentation
 * hooks into HTTP/Koa before they're loaded.
 *
 * Env vars:
 *   OTEL_EXPORTER_OTLP_ENDPOINT — collector URL (default: http://localhost:4318)
 *   OTEL_SERVICE_NAME            — service name (default: chatrag-backend)
 *   OTEL_ENABLED                 — set to "false" to disable (default: true)
 */
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http'
import { KoaInstrumentation } from '@opentelemetry/instrumentation-koa'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { NodeSDK } from '@opentelemetry/sdk-node'
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions'

const enabled = (process.env.OTEL_ENABLED ?? 'true').toLowerCase()
if (enabled === 'false' || enabled === '0') {
  console.log('[OTel] Disabled via OTEL_ENABLED=false')
} else {
  const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? 'http://localhost:4318'
  const serviceName = process.env.OTEL_SERVICE_NAME ?? 'chatrag-backend'

  const sdk = new NodeSDK({
    resource: resourceFromAttributes({ [ATTR_SERVICE_NAME]: serviceName }),
    traceExporter: new OTLPTraceExporter({ url: `${endpoint}/v1/traces` }),
    metricReader: new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({ url: `${endpoint}/v1/metrics` }),
      exportIntervalMillis: 15_000,
    }),
    instrumentations: [new HttpInstrumentation(), new KoaInstrumentation()],
  })

  sdk.start()
  console.log(`[OTel] Initialized — endpoint=${endpoint} service=${serviceName}`)

  // Graceful shutdown
  process.on('SIGTERM', () => sdk.shutdown())
  process.on('SIGINT', () => sdk.shutdown())
}
