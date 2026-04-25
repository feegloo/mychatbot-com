import { test, expect } from '@playwright/test'

const RUN_REAL_IMAGE_STREAM = process.env.PW_REAL_OPENAI_IMAGE_STREAM_TEST === '1'
const REAL_PROMPT =
  process.env.PW_REAL_OPENAI_IMAGE_PROMPT ||
  'Generate image inspired by a calm minimalist breathing scene with soft morning light 🎨'

test.describe('Real image streaming morph', () => {
  test.skip(
    !RUN_REAL_IMAGE_STREAM,
    'Set PW_REAL_OPENAI_IMAGE_STREAM_TEST=1 to run live OpenAI image-stream E2E.',
  )

  test('shows morph partials during real generation and ends with final image', async ({ page }) => {
    test.setTimeout(360_000)

    await page.goto('/')

    const streamResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes('/generate-image-stream'),
      { timeout: 60_000 },
    )

    const input = page.locator('.chat-textarea').first()
    await expect(input).toBeVisible()
    await input.fill(REAL_PROMPT)
    await page.locator('.send-btn').first().click()

    const generatingLabel = page.locator('.image-generating-label').last()
    await expect(generatingLabel).toBeVisible({ timeout: 60_000 })

    const morphImage = page.locator('.image-morph-wrap img').last()
    await expect(morphImage).toBeVisible({ timeout: 180_000 })

    const firstMorphSrc = await morphImage.getAttribute('src')
    expect(firstMorphSrc).toBeTruthy()
    expect(firstMorphSrc ?? '').toMatch(/^data:image\/(png|jpeg);base64,/)

    const initialFilter = await morphImage.evaluate((el) =>
      window.getComputedStyle(el as HTMLImageElement).filter,
    )
    expect(initialFilter).toContain('blur')

    const streamResponse = await streamResponsePromise
    const streamBody = await streamResponse.text()
    expect(streamBody).toContain('event: partial')

    const finalAssistantImage = page.locator('.message.assistant .markdown-image-scroll img').last()
    await expect(finalAssistantImage).toBeVisible({ timeout: 240_000 })

    await expect(page.locator('.image-morph-wrap')).toHaveCount(0)
    await expect(page.locator('.image-generating-label')).toHaveCount(0)
  })
})
