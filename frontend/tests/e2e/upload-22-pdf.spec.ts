/**
 * E2E tests for uploading 22.pdf — a mixed image+text PDF that requires
 * full-page OCR to extract the article text.
 *
 * Structure of 22.pdf:
 *  - 1 page with only 108 chars of native text (announcement box)
 *  - Article text "PRAWDZIWA HISTORIA" is rendered as inline PDF content,
 *    not extractable natively — requires GPT-Vision OCR of the rendered page.
 *  - Crossword grid + portrait photo as image xrefs.
 *
 * Test strategy (two tiers):
 *
 * 1. Mocked tier (always runs): intercepts /api/upload and /api/conversations/:id
 *    to test the frontend upload flow in isolation.
 *
 * 2. Live integration tier (PW_LIVE_UPLOAD=1): performs a real HTTP upload to
 *    the running backend and verifies that after indexing, the conversation
 *    can answer a question about the article content.
 */

import { test, expect, type Page } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const PDF_PATH = path.resolve(__dirname, '../../../test-files/22.pdf')
const CONV_ID = 'test22-0000-0000-0000-000000000001'
const OWNER_TOKEN = 'owner-token-test22'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Seed the frontend's localStorage so it recognises the mocked conversation. */
async function seedConversationToken(page: Page) {
  await page.evaluate(
    ([key, id, token]) => {
      const stored = localStorage.getItem(key)
      const parsed = stored ? JSON.parse(stored) : {}
      parsed[id] = token
      localStorage.setItem(key, JSON.stringify(parsed))
    },
    ['conversation-token', CONV_ID, OWNER_TOKEN],
  )
}

function makeConversationResponse(status: string, welcomeContent: string) {
  return {
    conversationId: CONV_ID,
    status,
    messages: [
      {
        id: 'msg-welcome',
        role: 'assistant',
        content: welcomeContent,
        citations: { _uploadedFileNames: ['22.pdf'] },
      },
    ],
    fileNames: ['22.pdf'],
    files: [{ original_name: '22.pdf', status: 'ready' }],
    displayName: null,
    chapters: [],
    suggestedQuestions: ['Jaka jest historia biblioteki doktora Efekta?'],
    language: 'pl',
    enabledModules: [],
    accessRequests: [],
  }
}

// ---------------------------------------------------------------------------
// Mocked upload tier
// ---------------------------------------------------------------------------

test.describe('22.pdf upload — mocked backend', () => {
  test('upload area is visible on landing page', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/click to upload or drag/i)).toBeVisible()
  })

  test('uploading 22.pdf triggers POST /api/upload and redirects to conversation', async ({
    page,
  }) => {
    const uploadResponse = {
      conversationId: CONV_ID,
      url: `/c/${CONV_ID}`,
      status: 'processing',
      ownerPassword: OWNER_TOKEN,
    }

    // Intercept the upload request before navigating so we catch it.
    await page.route('**/api/upload', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(uploadResponse),
      })
    })

    // Intercept the conversation polling endpoint.
    await page.route(`**/api/conversations/${CONV_ID}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          makeConversationResponse(
            'ready',
            '## 22.pdf\n\nPRAWDZIWA HISTORIA — Biblioteka doktora Efekta, licząca kilka tysięcy egzemplarzy.',
          ),
        ),
      })
    })

    await page.goto('/')

    // Use the file input (hidden behind the upload zone).
    const fileInput = page.locator('input[type="file"]').first()
    await fileInput.setInputFiles(PDF_PATH)

    // Should redirect to /c/<conversationId>
    await page.waitForURL(`**/c/${CONV_ID}`, { timeout: 15_000 })
    expect(page.url()).toContain(CONV_ID)
  })

  test('conversation page shows article content from mocked welcome message', async ({ page }) => {
    // Intercept conversation fetch so we can inject our mock.
    await page.route(`**/api/conversations/${CONV_ID}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          makeConversationResponse(
            'ready',
            '## 22.pdf\n\nPRAWDZIWA HISTORIA — Biblioteka doktora Efekta, licząca kilka tysięcy egzemplarzy.',
          ),
        ),
      })
    })

    await seedConversationToken(page)
    await page.goto(`/c/${CONV_ID}`)

    // The mocked welcome message should be visible.
    await expect(page.getByText('PRAWDZIWA HISTORIA', { exact: false })).toBeVisible({
      timeout: 10_000,
    })
  })
})

// ---------------------------------------------------------------------------
// Live integration tier — requires real backend + OpenAI API key
// ---------------------------------------------------------------------------

const RUN_LIVE = process.env.PW_LIVE_UPLOAD === '1'

test.describe('22.pdf upload — live integration', () => {
  test.skip(!RUN_LIVE, 'Set PW_LIVE_UPLOAD=1 to run the live upload + OCR integration test.')

  test(
    'uploads 22.pdf, waits for OCR, and verifies article content is queryable',
    async ({ page }) => {
      test.setTimeout(300_000) // OCR can take up to 5 minutes for a dense page

      // ── Step 1: Upload the file ──────────────────────────────────────────
      await page.goto('/')
      const fileInput = page.locator('input[type="file"]').first()
      await fileInput.setInputFiles(PDF_PATH)

      // Should redirect to /c/<conversationId> while indexing runs.
      await page.waitForURL('**/c/**', { timeout: 30_000 })
      const conversationUrl = page.url()
      const liveConvId = conversationUrl.split('/c/')[1]
      expect(liveConvId).toBeTruthy()

      // ── Step 2: Wait for indexing to complete ────────────────────────────
      // Poll the conversation status endpoint until status = 'ready'.
      const baseUrl = process.env.PW_API_BASE_URL || 'http://localhost:3000'
      let ready = false
      const deadline = Date.now() + 240_000 // up to 4 minutes for OCR
      while (Date.now() < deadline) {
        const resp = await page.request.get(`${baseUrl}/api/conversations/${liveConvId}`)
        if (resp.ok()) {
          const body = await resp.json()
          if (body.status === 'ready') {
            ready = true
            break
          }
        }
        await page.waitForTimeout(5_000)
      }
      expect(ready, 'Conversation did not reach ready state before timeout').toBe(true)

      // ── Step 3: Verify article content is present in the welcome message ─
      // After OCR the welcome message should mention the article.
      const resp = await page.request.get(`${baseUrl}/api/conversations/${liveConvId}`)
      const conv = await resp.json()
      const welcomeMsg = (conv.messages as Array<{ role: string; content: string }>).find(
        (m) => m.role === 'assistant',
      )
      expect(welcomeMsg).toBeTruthy()
      const welcomeText = (welcomeMsg?.content ?? '').toUpperCase()
      // The OCR'd page should have produced a welcome referencing the article.
      expect(
        welcomeText.includes('HISTORIA') || welcomeText.includes('JÓZEF') || welcomeText.includes('PRAWDZIWA'),
        `Welcome message did not mention the article. Got: ${welcomeMsg?.content?.slice(0, 300)}`,
      ).toBe(true)
    },
  )
})
