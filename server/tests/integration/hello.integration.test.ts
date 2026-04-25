import { describe, expect, it } from 'vitest'
import request from 'supertest'

import { createApp } from '../../src/app.js'

describe('GET /hello (integration)', () => {
  it('returns message from injected provider', async () => {
    const app = createApp({
      getMessage: () => 'hello from integration test',
    })

    const response = await request(app.callback()).get('/hello')

    expect(response.status).toBe(200)
    expect(response.body).toEqual({ message: 'hello from integration test' })
  })
})
