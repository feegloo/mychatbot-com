import { test, expect } from '@playwright/test'

test('landing page renders upload UI', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText(/click to upload or drag/i)).toBeVisible()
})
