import * as Sentry from '@sentry/node'

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT || 'dev',
  sendDefaultPii: true,
  tracesSampleRate: 1.0,
  enableLogs: true,
  integrations: [Sentry.consoleLoggingIntegration({ levels: ['warn', 'error'] })],
  beforeSend: (event, hint) => {
    // Drop OpenTelemetry exporter noise (OTLP collector not reachable in Cloud Run)
    const err = hint?.originalException as Error | undefined
    const msg = err?.message || event.message || ''
    const stack = err?.stack || ''
    if (
      /opentelemetry|OTLPExporter|otlp/i.test(stack) ||
      (/ECONNREFUSED/i.test(msg) && /:4318/.test(msg))
    ) {
      return null
    }
    return event
  },
  beforeSendLog: (log) => {
    if (process.env.NODE_ENV === 'production' && log.level === 'debug') {
      return null
    }
    return log
  },
})
