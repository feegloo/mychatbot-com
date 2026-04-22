import './otel.js'
import './instrument.js'
import { createApp } from './app.js'
import { config } from './config.js'
import { ensureDebugIndexes } from './db.js'

const app = createApp()

app.listen(config.port, () => {
  console.log(`Backend listening on http://localhost:${config.port}`)
  // Fire-and-forget: keeps /debug page snappy across fresh deploys without
  // requiring an out-of-band migration step.
  ensureDebugIndexes().catch((err) => {
    console.warn('[startup] ensureDebugIndexes failed:', err)
  })
})
