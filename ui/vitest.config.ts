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
      // dexie lives in ui/node_modules but is imported from frontend/src which has no node_modules.
      // Pin the alias so Vitest can always find it.
      dexie: fileURLToPath(new URL('./node_modules/dexie/dist/dexie.mjs', import.meta.url)),
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
