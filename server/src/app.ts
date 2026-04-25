import Koa from 'koa'
import Router from '@koa/router'

import { buildHelloPayload, type HelloMessageProvider } from './hello-response.js'

type CreateAppOptions = {
  getMessage?: HelloMessageProvider
}

export function createApp(options: CreateAppOptions = {}) {
  const app = new Koa()
  const router = new Router()

  router.get('/hello', (ctx) => {
    ctx.body = buildHelloPayload(options.getMessage)
  })

  app.use(router.routes())
  app.use(router.allowedMethods())

  return app
}
