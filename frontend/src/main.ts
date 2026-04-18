import { createApp } from "vue";
import FloatingVue from "floating-vue";
import "floating-vue/dist/style.css";
import * as Sentry from "@sentry/vue";
import App from "./App.vue";
import router from "./router";
import "./style.css";

const app = createApp(App);

Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE === "production" ? "prod" : "dev",
  integrations: [
    Sentry.browserTracingIntegration({ router }),
    Sentry.replayIntegration(),
  ],
  sendDefaultPii: true,
  tracesSampleRate: 1.0,
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,
});

app.use(router).use(FloatingVue).mount("#app");
