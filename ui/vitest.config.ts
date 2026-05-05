import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    dedupe: ['vue'],
    alias: {
      '@frontend-home-hero': fileURLToPath(
        new URL('../frontend/src/components/HomeHero.vue', import.meta.url),
      ),
      // dexie is a frontend dependency not installed in ui/node_modules; stub it for tests.
      dexie: fileURLToPath(new URL('./src/__mocks__/dexie.ts', import.meta.url)),
    },
  },
  server: {
    fs: {
      allow: [fileURLToPath(new URL('..', import.meta.url))],
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
    },
  },
})
