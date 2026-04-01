import { test, expect } from "@playwright/test";

test("landing page renders upload UI", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Upload files")).toBeVisible();
  await expect(page.getByText("Drag and drop")).toBeVisible();
});
