import Koa from 'koa'
import cors from '@koa/cors'
import bodyParser from 'koa-bodyparser'
import path from 'node:path'
import fs from 'node:fs'
import send from 'koa-send'
import * as Sentry from '@sentry/node'
import { uploadRouter } from './routes/upload.js'
import { conversationsRouter } from './routes/conversations.js'
import { askRouter } from './routes/ask.js'
import { healthRouter } from './routes/health.js'
import { storageRouter } from './routes/storage.js'
import { debugRouter } from './routes/debug.js'
import { translateRouter } from './routes/translate.js'
import { synthesizeRouter } from './routes/synthesize.js'
import { donateRouter } from './routes/donate.js'
import { imageGenRouter } from './routes/image-gen.js'
import { config } from './config.js'
import logger from './logger.js'
import { requestIdMiddleware } from './middleware/requestId.js'

export function createApp() {
  const app = new Koa()

  app.on('error', (err) => {
    Sentry.captureException(err)
  })

  app.use(cors({ exposeHeaders: ['X-Request-Id'] }))
  app.use(bodyParser())
  app.use(requestIdMiddleware)

  Sentry.setupKoaErrorHandler(app)

  const apiRouter = uploadRouter
    .use(conversationsRouter.routes())
    .use(askRouter.routes())
    .use(healthRouter.routes())
    .use(storageRouter.routes())
    .use(translateRouter.routes())
    .use(synthesizeRouter.routes())
    .use(donateRouter.routes())
    .use(imageGenRouter.routes())

  // Debug routes are mounted directly at /api/debug/* — no /api prefix stripping.
  // This keeps the externally-visible path explicit and avoids conflicting with
  // the stripping middleware below.
  app.use(debugRouter.routes())
  app.use(debugRouter.allowedMethods())

  // Direct health check — Cloud Run startup/liveness probes hit the container
  // at /health bypassing the LB (which only routes /api/* to Cloud Run).
  app.use(async (ctx, next) => {
    if (ctx.path === '/health') {
      ctx.body = { ok: true }
      return
    }
    return next()
  })

  app.use(async (ctx, next) => {
    if (ctx.path.startsWith('/api2')) {
      const target = `${config.serverUrl}${ctx.path}${ctx.querystring ? '?' + ctx.querystring : ''}`
      const response = await fetch(target, { method: ctx.method })
      ctx.status = response.status
      ctx.body = await response.json()
      return
    }
    return next()
  })

  // Serve .well-known files explicitly (extensionless files need content-type set)
  app.use(async (ctx, next) => {
    if (ctx.path.startsWith('/.well-known/')) {
      const distRoot = path.resolve(config.frontendDistPath)
      // Try exact path first, then without .txt extension
      const candidates = [ctx.path, ctx.path.replace(/\.txt$/, '')]
      for (const candidate of candidates) {
        const resolved = path.resolve(path.join(distRoot, candidate))
        if (!resolved.startsWith(distRoot)) continue
        if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
          ctx.type = 'text/plain'
          ctx.body = fs.createReadStream(resolved)
          return
        }
      }
    }
    return next()
  })

  app.use(async (ctx, next) => {
    if (ctx.path.startsWith('/api') && !ctx.path.startsWith('/api/debug')) {
      ctx.path = ctx.path.replace(/^\/api/, '') || '/'
      const start = Date.now()
      const sentryTrace = ctx.get('sentry-trace') || undefined
      const baggage = ctx.get('baggage') || undefined
      const traceId = (ctx.state.traceId as string | undefined) || ''

      await Sentry.continueTrace({ sentryTrace, baggage }, async () => {
        await Sentry.startSpan(
          {
            name: `${ctx.method} ${ctx.path}`,
            op: 'http.server',
            forceTransaction: true,
            attributes: {
              'http.method': ctx.method,
              'http.route': ctx.path,
              'chatrag.trace_id': traceId,
            },
          },
          async () => {
            if (traceId) {
              Sentry.setTag('trace_id', traceId)
            }
            try {
              await apiRouter.routes()(ctx as any, next)
            } catch (err: any) {
              const status = err.status || err.statusCode || 500
              const message = err.message || 'Unknown error'
              logger.error(
                {
                  err,
                  method: ctx.method,
                  url: ctx.url,
                  status,
                  durationMs: Date.now() - start,
                  traceId,
                },
                'API error',
              )
              if (status >= 500) Sentry.captureException(err)
              ctx.status = status
              ctx.body = { error: message, stack: err.stack || null }
              return
            }
          },
        )
      })

      const durationMs = Date.now() - start
      if (durationMs > 500) {
        logger.warn(
          { method: ctx.method, url: ctx.url, status: ctx.status, durationMs, traceId },
          'Slow API request',
        )
      }
      return
    }
    return next()
  })

  // Serve the ui SPA (built with base /v2/) for all /v2/* requests.
  // Static assets (hashed filenames) get long-lived cache; HTML gets revalidation.
  app.use(async (ctx, next) => {
    if (!ctx.path.startsWith('/v2')) return next()
    if (!config.uiDistPath || !fs.existsSync(config.uiDistPath)) return next()

    const uiRoot = path.resolve(config.uiDistPath)
    // Strip /v2 prefix to get the path relative to the ui dist root
    const relativePath = ctx.path.replace(/^\/v2/, '') || '/'
    const ext = path.extname(relativePath)

    if (ext && ext !== '.html') {
      // Serve static asset directly; 404 if not found
      const filePath = path.resolve(path.join(uiRoot, relativePath))
      if (!filePath.startsWith(uiRoot)) {
        ctx.status = 400
        return
      }
      if (!fs.existsSync(filePath)) {
        ctx.status = 404
        return
      }
      await send(ctx, relativePath, { root: uiRoot })
      if (relativePath.startsWith('/assets/')) {
        ctx.set('Cache-Control', 'public, max-age=31536000, immutable')
      }
      return
    }

    // All navigable routes (/v2/, /v2/c/:uid) return index.html for SPA routing
    await send(ctx, 'index.html', { root: uiRoot })
    ctx.set('Cache-Control', 'public, max-age=0, must-revalidate')
  })

  return app
}
