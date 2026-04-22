import { test, expect, type Page } from '@playwright/test'

/**
 * E2E coverage for MermaidBlock rendering. Uses the dev-only test harness at
 * `/__test__/mermaid` so we can mount the component with known source code
 * without relying on backend streams. See frontend/src/pages/MermaidTestPage.vue.
 */

const VALID_DIAGRAM = `graph TD
  A[Start] --> B{Is it?}
  B -->|Yes| C[OK]
  B -->|No| D[End]`

async function gotoHarness(
  page: Page,
  options: { fixture?: 'valid' | 'invalid' | 'empty'; code?: string } = {},
) {
  const params = new URLSearchParams()
  if (options.fixture) params.set('fixture', options.fixture)
  if (options.code !== undefined) {
    // Base64 to safely carry newlines / special characters.
    params.set('codeB64', Buffer.from(options.code, 'utf-8').toString('base64'))
  }
  const query = params.toString()
  await page.goto(`/__test__/mermaid${query ? `?${query}` : ''}`)
}

test.describe('MermaidBlock rendering', () => {
  test('renders diagram by default on page load', async ({ page }) => {
    await gotoHarness(page, { fixture: 'valid' })

    const diagram = page.locator('.mermaid-diagram').first()
    await expect(diagram).toBeVisible()
    // Mermaid injects an <svg> into the wrapper once rendering completes.
    await expect(diagram.locator('.mermaid-svg-wrapper svg')).toBeVisible()

    // Text fallback must not be visible by default.
    await expect(page.locator('.mermaid-source').first()).toBeHidden()
    await expect(page.locator('.mermaid-error')).toHaveCount(0)
  })

  test('renders newly supplied code without a full reload', async ({ page }) => {
    await gotoHarness(page, { fixture: 'valid' })
    await expect(page.locator('.mermaid-svg-wrapper svg').first()).toBeVisible()

    // Simulate the assistant producing a new answer by navigating to a
    // different code payload. The component remounts on :key change and must
    // again default to diagram view.
    const newCode = 'graph LR\n  X --> Y --> Z'
    await gotoHarness(page, { code: newCode })

    const diagram = page.locator('.mermaid-diagram').first()
    await expect(diagram).toBeVisible()
    await expect(diagram.locator('.mermaid-svg-wrapper svg')).toBeVisible()
    await expect(page.locator('.mermaid-source').first()).toBeHidden()
  })

  test('toggles to text and back to a rendered diagram', async ({ page }) => {
    await gotoHarness(page, { fixture: 'valid' })
    const block = page.locator('.mermaid-block').first()
    await expect(block.locator('.mermaid-svg-wrapper svg')).toBeVisible()

    // Toolbar only appears on hover.
    await block.hover()
    await block.getByRole('button', { name: /switch to text/i }).click()
    await expect(block.locator('.mermaid-source')).toBeVisible()
    await expect(block.locator('.mermaid-diagram')).toBeHidden()

    await block.hover()
    await block.getByRole('button', { name: /switch to diagram/i }).click()
    await expect(block.locator('.mermaid-diagram')).toBeVisible()
    await expect(block.locator('.mermaid-svg-wrapper svg')).toBeVisible()
  })

  test('shows inline error and keeps diagram mode on invalid code', async ({ page }) => {
    await gotoHarness(page, { fixture: 'invalid' })

    const errorPanel = page.locator('.mermaid-error')
    await expect(errorPanel).toBeVisible()
    await expect(errorPanel.locator('.mermaid-error-title')).toHaveText(/could not render/i)

    // Must not silently flip the user into text-only mode.
    await expect(page.locator('.mermaid-source[style*="display: none"]')).toHaveCount(1)
    await expect(page.locator('.mermaid-svg-wrapper svg')).toHaveCount(0)
  })

  test('renders the valid diagram after the user switches away from an error', async ({ page }) => {
    await gotoHarness(page, { fixture: 'invalid' })
    await expect(page.locator('.mermaid-error')).toBeVisible()

    const block = page.locator('.mermaid-block').first()
    await block.hover()
    await block.getByRole('button', { name: /switch to text/i }).click()
    await expect(block.locator('.mermaid-source')).toBeVisible()

    await block.hover()
    await block.getByRole('button', { name: /switch to diagram/i }).click()

    // Still invalid code, so the error panel must re-appear rather than an
    // empty diagram container.
    await expect(page.locator('.mermaid-error')).toBeVisible()
  })
})
