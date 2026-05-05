import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  base: '/v2/',
  plugins: [vue()],
  resolve: {
    dedupe: ['vue'],
    alias: {
      '@frontend-home-hero': fileURLToPath(
        new URL('../frontend/src/components/HomeHero.vue', import.meta.url),
      ),
      // dexie is used by frontend/src components imported via @frontend-home-hero.
      // Since frontend/src lives outside ui/, rolldown cannot walk up to ui/node_modules,
      // so we explicitly point the specifier at the installed package.
      'dexie': fileURLToPath(new URL('node_modules/dexie', import.meta.url)),
    },
  },
  server: {
    fs: {
      allow: [fileURLToPath(new URL('..', import.meta.url))],
    },
    proxy: {
      '/api2': 'http://localhost:4300',
    },
  },
})
