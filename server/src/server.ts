import type { Server } from 'node:http'

import { createApp } from './app.js'

type StartServerOptions = {
  port?: number
}

export function startServer(options: StartServerOptions = {}): Server {
  const port = options.port ?? Number(process.env.PORT || 4300)
  const app = createApp()

  const server = app.listen(port, () => {
    console.log(`node migration boilerplate listening on http://localhost:${port}`)
  })

  return server
}
