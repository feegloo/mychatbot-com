import { expect, test } from '@playwright/test'

test('renders the imported HomeHero inside the right column', async ({ page }) => {
  await page.goto('/')

  const menuColumn = page.getByTestId('menu-column')
  const contentColumn = page.getByTestId('content-column')

  await expect(menuColumn).toBeVisible()
  await expect(contentColumn).toBeVisible()
  await expect(page.getByAltText('chatrag.app')).toBeVisible()
  await expect(page.getByText('Upload securely 🔒 and chat with your Big PDFs and files')).toBeVisible()

  const menuBackground = await menuColumn.evaluate(
    (element) => window.getComputedStyle(element).backgroundColor,
  )
  const contentBackground = await contentColumn.evaluate(
    (element) => window.getComputedStyle(element).backgroundColor,
  )

  expect(menuBackground).toBe('rgb(31, 41, 55)')
  expect(contentBackground).toBe('rgb(243, 244, 246)')
})
