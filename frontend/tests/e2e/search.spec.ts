/**
 * E2E tests for the conversation search feature in ConversationNav.
 *
 * Strategy: We seed localStorage with fake conversation tokens so the
 * app believes the user owns some conversations, then intercept the two
 * API calls the search feature makes:
 *   POST /api/conversations/batch   → returns ConversationSummary[]
 *   GET  /api/conversations/:id     → returns full conversation with messages
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const TOKENS_STORAGE_KEY = 'conversation-token'
const APP_URL = process.env.E2E_BASE_URL || 'http://localhost:5173/'

const CONV_ALPHA_ID = 'aaa00000-0000-0000-0000-000000000001'
const CONV_BRAVO_ID = 'bbb00000-0000-0000-0000-000000000002'

const FAKE_TOKENS = {
  [CONV_ALPHA_ID]: 'token-alpha',
  [CONV_BRAVO_ID]: 'token-bravo',
}

const BATCH_RESPONSE = {
  conversations: [
    { conversationId: CONV_ALPHA_ID, displayName: 'Alpha Chat', status: 'ready', fileNames: [] },
    { conversationId: CONV_BRAVO_ID, displayName: 'Bravo Chat', status: 'ready', fileNames: [] },
  ],
}

function makeConversationResponse(conversationId: string, messages: { id: string; role: string; content: string }[]) {
  return {
    conversationId,
    status: 'ready',
    messages,
    fileNames: [],
    displayName: null,
    chapters: [],
    suggestedQuestions: [],
    language: 'en',
    enabledModules: [],
  }
}

const ALPHA_CONVERSATION = makeConversationResponse(CONV_ALPHA_ID, [
  { id: 'msg-a1', role: 'user', content: 'Tell me about the Alchemist book by Paulo Coelho.' },
  { id: 'msg-a2', role: 'assistant', content: 'The Alchemist is about Santiago finding his destiny.' },
])

const BRAVO_CONVERSATION = makeConversationResponse(CONV_BRAVO_ID, [
  { id: 'msg-b1', role: 'user', content: 'What is the Dance With Dragons about?' },
  { id: 'msg-b2', role: 'assistant', content: 'A Song of Ice and Fire. Dragons. Jon Snow.' },
])

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function seedConversations(page: import('@playwright/test').Page) {
  await page.goto(APP_URL)

  // Seed tokens so the app knows the user owns these conversations.
  await page.evaluate(
    ([key, value]) => localStorage.setItem(key, value),
    [TOKENS_STORAGE_KEY, JSON.stringify(FAKE_TOKENS)],
  )

  // Intercept batch summary request.
  await page.route('**/api/conversations/batch', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BATCH_RESPONSE),
    })
  })

  // Intercept per-conversation detail requests.
  await page.route(`**/api/conversations/${CONV_ALPHA_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ALPHA_CONVERSATION),
    })
  })

  await page.route(`**/api/conversations/${CONV_BRAVO_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(BRAVO_CONVERSATION),
    })
  })

  // Reload so the seeded localStorage and route mocks take effect.
  await page.reload()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Conversation search – sidebar', () => {
  test('search button is visible in the sidebar', async ({ page }) => {
    await page.goto(APP_URL)

    const searchBtn = page.locator('.conv-nav-search-btn')
    await expect(searchBtn).toBeVisible()
  })

  test('clicking search button shows search panel', async ({ page }) => {
    await page.goto(APP_URL)

    const searchBtn = page.locator('.conv-nav-search-btn')
    await searchBtn.click()

    const searchInput = page.locator('.conv-nav-search-input')
    await expect(searchInput).toBeVisible()
  })

  test('clicking search button again closes search panel', async ({ page }) => {
    await page.goto(APP_URL)

    const searchBtn = page.locator('.conv-nav-search-btn')
    await searchBtn.click()
    await expect(page.locator('.conv-nav-search-input')).toBeVisible()

    await searchBtn.click()
    await expect(page.locator('.conv-nav-search-input')).not.toBeVisible()
  })

  test('clicking magnifying glass again closes search panel', async ({ page }) => {
    await page.goto(APP_URL)

    const searchBtn = page.locator('.conv-nav-search-btn')
    await searchBtn.click()
    await expect(page.locator('.conv-nav-search-input')).toBeVisible()

    await searchBtn.click()
    await expect(page.locator('.conv-nav-search-input')).not.toBeVisible()
  })

  test('search input is focused when panel opens', async ({ page }) => {
    await page.goto(APP_URL)

    await page.locator('.conv-nav-search-btn').click()

    const searchInput = page.locator('.conv-nav-search-input')
    await expect(searchInput).toBeFocused()
  })

  test('typing fewer than 4 characters shows "at least 4 characters" hint', async ({ page }) => {
    await page.goto(APP_URL)

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('abc')

    // The hint paragraph in the conversation list area
    const hint = page.locator('.conv-nav-empty')
    await expect(hint).toBeVisible()
    await expect(hint).toContainText(/at least 4/i)
  })

  test('typing exactly 4 characters does not show "at least 4" warning', async ({ page }) => {
    await seedConversations(page)

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('alch')

    // Wait for debounce + search to complete (max 2s to be safe)
    await page.waitForTimeout(900)

    const emptyHint = page.locator('.conv-nav-empty')
    // Should NOT show the "at least 4 characters" message
    await expect(emptyHint).not.toContainText(/at least 4/i)
  })

  test('search filters conversation list to only matching conversations', async ({ page }) => {
    await seedConversations(page)

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('alchemist')

    // Wait for debounce (700ms) + search time
    await page.waitForTimeout(900)

    const navItems = page.locator('.conv-nav-item')
    await expect(navItems).toHaveCount(1)
    await expect(navItems.first()).toContainText('Alpha Chat')
  })

  test('match count badge appears on matching conversations', async ({ page }) => {
    await seedConversations(page)

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('alchemist')

    await page.waitForTimeout(900)

    const badge = page.locator('.conv-nav-search-count')
    await expect(badge).toBeVisible()
    // "alchemist" appears twice in ALPHA_CONVERSATION
    await expect(badge).toHaveText('2')
  })

  test('search with no matches shows "No matches found"', async ({ page }) => {
    await seedConversations(page)

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('zzznomatch')

    await page.waitForTimeout(900)

    const emptyMsg = page.locator('.conv-nav-empty')
    await expect(emptyMsg).toBeVisible()
    await expect(emptyMsg).toContainText(/no matches/i)
  })

  test('finishing search restores full conversation list', async ({ page }) => {
    await seedConversations(page)

    const navItems = page.locator('.conv-nav-item')

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('alchemist')
    await page.waitForTimeout(900)

    // While searching, only 1 conversation visible
    await expect(navItems).toHaveCount(1)

    await page.locator('.conv-nav-search-btn').click()

    // After finishing, all conversations restored
    await expect(navItems).toHaveCount(2)
  })

  test('clicking a matching conversation navigates with search query params', async ({ page }) => {
    await seedConversations(page)

    await page.locator('.conv-nav-search-btn').click()
    await page.locator('.conv-nav-search-input').fill('alchemist')

    await page.waitForTimeout(900)

    await page.locator('.conv-nav-item').first().click()

    await expect(page).toHaveURL(new RegExp(`/c/${CONV_ALPHA_ID}`))
    await expect(page).toHaveURL(/searchTerm=alchemist/)
  })
})
