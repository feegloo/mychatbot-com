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
