import { expect, test } from "@playwright/test";

const publicPages = ["/", "/technology", "/wellness-start", "/about", "/contact", "/publications"];
const widths = [390, 430, 768, 1024, 1440];

test.describe("Public website responsive contract", () => {
  for (const width of widths) {
    test(`public home has no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/?lang=pl");
      const dimensions = await page.evaluate(() => ({
        client: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
    });
  }

  test("mobile menu is keyboard-operable and preserves public links", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/?lang=pl");
    const menu = page.getByRole("button", { name: "Menu" });
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await menu.focus();
    await page.keyboard.press("Enter");
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("link", { name: "Start Wellness" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu).toHaveAttribute("aria-expanded", "false");
  });

  test("public commercial pages remain reachable in English and Polish", async ({ page }) => {
    for (const path of publicPages) {
      await page.goto(`${path}?lang=en`);
      await expect(page.locator("main")).toBeVisible();
      await page.goto(`${path}?lang=pl`);
      await expect(page.locator("main")).toBeVisible();
    }
  });
});
