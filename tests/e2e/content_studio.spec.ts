import { expect, test } from "@playwright/test";


test.describe("Content Studio workflow surfaces", () => {
  test("Characters presents the active character and planned-library context", async ({ page }) => {
    await page.goto("/content-studio/characters");

    await expect(page.getByRole("heading", { name: "Characters" })).toBeVisible();
    await expect(page.getByText("not selectable yet")).toBeVisible();
    await expect(page.getByRole("link", { name: "CoreLabTech Athlete" })).toBeVisible();
  });

  test("Generate uses the configured provider capability contract", async ({ page }) => {
    await page.goto("/content-studio/generate");

    const provider = page.getByLabel("Provider");
    const output = page.getByLabel("Output");
    await expect(provider).toHaveValue("mock");
    await expect(output.getByRole("option", { name: "Image" })).toBeEnabled();
    await expect(output.getByRole("option", { name: /Video/ })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Generate" })).toBeEnabled();
  });

  test("Generated Media provides a stable library state and navigation back to Generate", async ({ page }) => {
    await page.goto("/content-studio/media");

    const library = page.locator("#media-list");
    await expect(library).toHaveAttribute("aria-busy", "false");
    expect(await library.locator(".media-library-state, .content-media-card").count()).toBeGreaterThan(0);

    if (await page.getByRole("link", { name: "Generate an asset" }).count()) {
      await page.getByRole("link", { name: "Generate an asset" }).click();
      await expect(page).toHaveURL(/\/content-studio\/generate$/);
    }
  });

  test("Content Studio navigation remains usable on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/content-studio/generate");

    await expect(page.getByLabel("Provider")).toBeVisible();
    await expect(page.getByRole("button", { name: "Generate" })).toBeVisible();
    await page.getByLabel("Provider").focus();
    await expect(page.getByLabel("Provider")).toBeFocused();
  });
});
