import { test, expect } from '@playwright/test'

const EMOJI_PROMPT = 'generate inspired image 🎨'
const DETAILED_PROMPT =
  'Ultra-detailed cinematic illustration of a quiet sunrise breathing ritual, soft haze, volumetric light, minimalist color grading.'
const TINY_PNG_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8B9kQAAAAASUVORK5CYII='

test.describe('Simulated image streaming morph', () => {
  test('renders 3 stages: generic, detailed prompt, then morphed image', async ({ page }) => {
    await page.addInitScript(({ detailedPrompt, tinyPngB64 }) => {
      const originalFetch = window.fetch.bind(window)

      const sseHeaders = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      }

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url

        if (url.includes('/api/announce-image')) {
          return new Response(JSON.stringify({ announcement: '' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/api/generate-image-stream')) {
          const encoder = new TextEncoder()
          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              setTimeout(() => {
                controller.enqueue(
                  encoder.encode(
                    `event: prompt_ready\ndata: ${JSON.stringify({ image_prompt: detailedPrompt, image_title: 'Sunrise Breath' })}\n\n`,
                  ),
                )
              }, 500)

              setTimeout(() => {
                controller.enqueue(
                  encoder.encode(
                    `event: partial\ndata: ${JSON.stringify({ b64: tinyPngB64, index: 0 })}\n\n`,
                  ),
                )
              }, 1100)

              setTimeout(() => {
                controller.enqueue(
                  encoder.encode(
                    `event: complete\ndata: ${JSON.stringify({ answer: 'Done.', citations: [] })}\n\n`,
                  ),
                )
                controller.close()
              }, 3000)
            },
          })

          return new Response(stream, { status: 200, headers: sseHeaders })
        }

        return originalFetch(input, init)
      }
    }, { detailedPrompt: DETAILED_PROMPT, tinyPngB64: TINY_PNG_B64 })

    await page.goto('/')

    const input = page.locator('.chat-textarea').first()
    await expect(input).toBeVisible()
    await input.fill(EMOJI_PROMPT)
    await page.locator('.send-btn').first().click()

    const genericLabel = page.locator('.image-generating-label').last()
    await expect(genericLabel).toBeVisible({ timeout: 10_000 })
    await expect(genericLabel).toContainText('Generating image, please wait...')

    const detailedPrompt = page.locator('.image-prompt-detail').last()
    await expect(detailedPrompt).toBeVisible({ timeout: 10_000 })
    await expect(detailedPrompt).toContainText('Ultra-detailed cinematic illustration')

    const morphImage = page.locator('.image-morph-wrap img').last()
    await expect(morphImage).toBeVisible({ timeout: 10_000 })
    const morphSrc = await morphImage.getAttribute('src')
    expect(morphSrc ?? '').toMatch(/^data:image\/png;base64,/)    
  })
})
