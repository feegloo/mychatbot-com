import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { sentryVitePlugin } from "@sentry/vite-plugin";

export default defineConfig({
  plugins: [
    vue(),
    // Must be after all other plugins so source maps are generated correctly
    sentryVitePlugin({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      disable: !process.env.SENTRY_AUTH_TOKEN,
      sourcemaps: {
        filesToDeleteAfterUpload: ["./dist/**/*.map"],
      },
    }),
  ],
  build: {
    sourcemap: "hidden",
    rollupOptions: {
      output: {
        manualChunks: {
          sentry: ["@sentry/vue"],
        },
      },
    },
  },
  server: {
    port: 5173
  }
});
