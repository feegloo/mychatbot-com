import * as Sentry from "@sentry/node";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT || "dev",
  sendDefaultPii: true,
  tracesSampleRate: 1.0,
  enableLogs: true,
  integrations: [
    Sentry.consoleLoggingIntegration({ levels: ["warn", "error"] }),
  ],
  beforeSendLog: (log) => {
    if (process.env.NODE_ENV === "production" && log.level === "debug") {
      return null;
    }
    return log;
  },
});
