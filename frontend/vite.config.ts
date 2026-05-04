import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import { execSync } from 'node:child_process'

function getCommitHash(): string {
  const envHash = [
    process.env.VITE_COMMIT_HASH,
    process.env.COMMIT_SHA,
    process.env.GITHUB_SHA,
    process.env.CI_COMMIT_SHA,
    process.env.SOURCE_VERSION,
  ]
    .map((value) => value?.trim())
    .find((value) => Boolean(value))

  if (envHash) {
    return envHash.slice(0, 12)
  }

  try {
    return execSync('git rev-parse --short HEAD', { stdio: ['pipe', 'pipe', 'ignore'] })
      .toString()
      .trim()
  } catch {
    return 'unknown'
  }
}
/**
 * Strips `woff` and `truetype` fallback `url(...)` entries from KaTeX's CSS so
 * only the `woff2` source survives. Every browser we support ships woff2 (it
 * has been baseline since ~2015), and dropping the fallbacks cuts the font
 * assets emitted into the build from 42 → 14 — making `vite build` and the
 * deploy upload step substantially faster without any visual change.
 */
function katexSlimFontsPlugin(): Plugin {
  const KATEX_CSS_RE = /[\\/]katex[\\/]dist[\\/]katex(?:\.min)?\.css(?:$|\?)/
  return {
    name: 'chatrag:katex-slim-fonts',
    enforce: 'pre',
    transform(code, id) {
      if (!KATEX_CSS_RE.test(id)) return null
      // Remove `,url(...woff) format("woff")` and `,url(...ttf) format("truetype")`
      // entries from each @font-face `src:` declaration.
      const slimmed = code.replace(
        /,\s*url\([^)]+\.(?:woff|ttf)\)\s*format\("(?:woff|truetype)"\)/g,
        '',
      )
      return { code: slimmed, map: null }
    },
  }
}

export default defineConfig({
  plugins: [
    vue(),
    katexSlimFontsPlugin(),
    // Must be after all other plugins so source maps are generated correctly
    sentryVitePlugin({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      disable: !process.env.SENTRY_AUTH_TOKEN,
      sourcemaps: {
        filesToDeleteAfterUpload: ['./dist/**/*.map'],
      },
    }),
  ],
  define: {
    __COMMIT_HASH__: JSON.stringify(getCommitHash()),
  },
  build: {
    sourcemap: 'hidden',
    rollupOptions: {
      output: {
        // Bundle all mermaid-related modules (including mermaid's own internal
        // dynamic sub-imports like mermaid.core) into a single chunk.
        // Without this, Vite splits mermaid into several lazy sub-chunks that
        // mermaid loads at runtime via its own import() calls; if any of those
        // chunks are missing from the deployment nginx returns a 404 (text/html)
        // which the browser rejects as an invalid module script.
        manualChunks(id: string) {
          if (id.includes('mermaid')) return 'mermaid'
          if (id.includes('@sentry/')) return 'sentry'
        },
      },
    },
  },
  server: {
    port: 5173,
  },
})
