import * as Sentry from "@sentry/node";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT || "dev",
  sendDefaultPii: true,
  tracesSampleRate: 1.0,
});
