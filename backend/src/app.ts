import Koa from 'koa'
import cors from '@koa/cors'
import bodyParser from 'koa-bodyparser'
import path from 'node:path'
import fs from 'node:fs'
import serve from 'koa-static'
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
    .use(debugRouter.routes())
    .use(translateRouter.routes())
    .use(synthesizeRouter.routes())
    .use(donateRouter.routes())
    .use(imageGenRouter.routes())

  app.use(async (ctx, next) => {
    if (ctx.path.startsWith('/api')) {
      ctx.path = ctx.path.replace(/^\/api/, '') || '/'
      const start = Date.now()
      try {
        await apiRouter.routes()(ctx as any, next)
      } catch (err: any) {
        const status = err.status || err.statusCode || 500
        const message = err.message || 'Unknown error'
        logger.error({ err, method: ctx.method, url: ctx.url, status, durationMs: Date.now() - start }, 'API error')
        if (status >= 500) Sentry.captureException(err)
        ctx.status = status
        ctx.body = { error: message, stack: err.stack || null }
        return
      }
      const durationMs = Date.now() - start
      if (durationMs > 500) {
        logger.warn({ method: ctx.method, url: ctx.url, status: ctx.status, durationMs }, 'Slow API request')
      }
      return
    }
    return next()
  })

  if (config.frontendDistPath && fs.existsSync(config.frontendDistPath)) {
    app.use(serve(config.frontendDistPath))

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

    app.use(async (ctx) => {
      if (ctx.path.startsWith('/api')) return
      // Don't serve index.html for missing static assets — return 404 instead
      const ext = path.extname(ctx.path)
      if (ext && ext !== '.html') {
        ctx.status = 404
        return
      }
      await send(ctx, 'index.html', { root: path.resolve(config.frontendDistPath) })
    })
  }

  return app
}
