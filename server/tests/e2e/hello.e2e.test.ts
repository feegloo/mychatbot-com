import type { AddressInfo } from 'node:net'

import { afterAll, describe, expect, it } from 'vitest'

import { startServer } from '../../src/server.js'

const server = startServer({ port: 0 })

afterAll(async () => {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error)
        return
      }
      resolve()
    })
  })
})

describe('GET /hello (e2e)', () => {
  it('returns response from running HTTP server', async () => {
    const address = server.address()
    if (!address || typeof address === 'string') {
      throw new Error('Failed to determine test server address')
    }

    const { port } = address as AddressInfo
    const response = await fetch(`http://127.0.0.1:${port}/hello`)
    const body = (await response.json()) as { message: string }

    expect(response.status).toBe(200)
    expect(body.message).toBeTypeOf('string')
    expect(body.message).toContain('Hello')
  })
})
