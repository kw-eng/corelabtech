import { expect, test } from "@playwright/test";

const publicPages = ["/", "/technology", "/wellness-start", "/about", "/contact", "/publications"];
const widths = [390, 430, 768, 1024, 1440];
const homeLocaleCopy = {
  pl: "Sesja w komorze jako udokumentowany workflow fizjologiczny",
  en: "A chamber session, viewed as a documented physiology workflow",
};

test.describe("Public website responsive contract", () => {
  test("public home renders the HBOT and report-preview structural sections", async ({ page }) => {
    for (const locale of ["pl", "en"] as const) {
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      await page.goto(`/?lang=${locale}`);
      await expect(page.locator(".home-hbot-context")).toBeVisible();
      await expect(page.locator(".home-report-preview")).toBeVisible();
      const hbotMedia = page.locator(".home-hbot-context .public-media");
      await expect(hbotMedia).toBeVisible();
      await expect.poll(
        () => hbotMedia.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0),
      ).toBe(true);
      await expect(page.locator(".home-hbot-context")).toContainText(homeLocaleCopy[locale]);
      expect(consoleErrors).toEqual([]);
    }
  });

  for (const width of widths) {
    for (const locale of ["pl", "en"] as const) {
      test(`public ${locale.toUpperCase()} home has no horizontal overflow at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(`/?lang=${locale}`);
        const dimensions = await page.evaluate(() => ({
          client: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
        }));
        expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
      });
    }
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
