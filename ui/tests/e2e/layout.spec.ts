import { expect, test } from '@playwright/test'

test('hello world: renders two columns with expected backgrounds', async ({ page }) => {
  await page.goto('/')

  const menuColumn = page.getByTestId('menu-column')
  const contentColumn = page.getByTestId('content-column')

  await expect(menuColumn).toBeVisible()
  await expect(contentColumn).toBeVisible()

  const menuBackground = await menuColumn.evaluate(
    (element) => window.getComputedStyle(element).backgroundColor,
  )
  const contentBackground = await contentColumn.evaluate(
    (element) => window.getComputedStyle(element).backgroundColor,
  )

  expect(menuBackground).toBe('rgb(31, 41, 55)')
  expect(contentBackground).toBe('rgb(243, 244, 246)')
})
