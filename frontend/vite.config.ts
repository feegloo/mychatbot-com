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
import { cp, stat } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createReadStream } from 'node:fs'
import { pipeline } from 'node:stream/promises'
import { fileURLToPath } from 'node:url'
import { dirname, resolve, sep } from 'node:path'
import { createRequire } from 'node:module'

const projectDir = dirname(fileURLToPath(import.meta.url))
const require = createRequire(import.meta.url)
// Locate pdfjs-dist package root via its package.json entry so we resolve the
// correct install regardless of hoisting.
const pdfjsDistDir = dirname(require.resolve('pdfjs-dist/package.json'))

// pdfjs-dist v5 ships several runtime asset folders that the PDF viewer needs
// to fully render documents — most importantly `wasm/` (JPEG2000/JBIG2 image
// decoders) and `iccs/` (ICC color profiles); without them embedded images in
// PDFs fail to render. `cmaps/` (CJK) and `standard_fonts/` are included for
// correct font fallbacks.
const PDFJS_ASSET_DIRS = (['wasm', 'iccs', 'cmaps', 'standard_fonts'] as const).filter((name) =>
  existsSync(resolve(pdfjsDistDir, name)),
)

/**
 * Copies pdfjs-dist runtime assets into the dev server (served from root under
 * `/pdfjs/...`) and into the production build output.
 */
function pdfjsAssetsPlugin(): Plugin {
  const assetRoute = '/pdfjs/'
  return {
    name: 'chatrag:pdfjs-assets',
    configureServer(server) {
      server.middlewares.use(assetRoute, async (req, res, next) => {
        try {
          const requestedUrl = req.url || '/'
          const cleaned = requestedUrl.split('?')[0].split('#')[0]
          const relative = decodeURIComponent(cleaned.replace(/^\/+/, ''))
          const [dir, ...rest] = relative.split('/')
          if (!PDFJS_ASSET_DIRS.includes(dir as (typeof PDFJS_ASSET_DIRS)[number])) {
            next()
            return
          }
          // Resolve and ensure the final path stays inside pdfjs-dist — defends
          // against traversal via `..` or absolute-path segments after decode.
          const filePath = resolve(pdfjsDistDir, dir, ...rest)
          const allowedRoot = resolve(pdfjsDistDir, dir)
          if (filePath !== allowedRoot && !filePath.startsWith(allowedRoot + sep)) {
            res.statusCode = 403
            res.end('Forbidden')
            return
          }
          const fileStat = await stat(filePath)
          if (!fileStat.isFile()) {
            next()
            return
          }
          res.setHeader(
            'Content-Type',
            filePath.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream',
          )
          res.setHeader('Content-Length', String(fileStat.size))
          // These assets are versioned alongside pdfjs-dist; safe to cache
          // aggressively in dev to avoid repeated disk reads on reload.
          res.setHeader('Cache-Control', 'public, max-age=3600')
          // Stream the file instead of buffering the whole asset into memory —
          // wasm/font blobs can be several MB.
          await pipeline(createReadStream(filePath), res)
        } catch (err) {
          const error = err as NodeJS.ErrnoException
          // Missing files fall through to Vite's default 404 handling via
          // `next()`. Unexpected filesystem/runtime errors should surface as
          // explicit 500 responses so they aren't masked as 404s.
          if (error?.code === 'ENOENT') {
            next()
            return
          }
          server.config.logger.warn(
            `[chatrag:pdfjs-assets] failed to serve ${req.url}: ${(err as Error).message}`,
          )
          if (!res.headersSent) {
            res.statusCode = 500
            res.end('Internal Server Error')
          } else {
            res.end()
          }
        }
      })
    },
    async writeBundle(outputOptions) {
      const outDir = resolve(projectDir, outputOptions.dir ?? 'dist')
      await Promise.all(
        PDFJS_ASSET_DIRS.map((name) =>
          cp(resolve(pdfjsDistDir, name), resolve(outDir, 'pdfjs', name), {
            recursive: true,
          }),
        ),
      )
    },
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
    pdfjsAssetsPlugin(),
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
