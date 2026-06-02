import { expect, Page } from "@playwright/test";

export async function loginAsAdmin(page: Page) {

  const response = await page.goto("/login", {
    waitUntil: "domcontentloaded",
    timeout: 15000,
  });

  console.log("LOGIN PAGE STATUS:", response?.status());
  console.log("LOGIN PAGE URL:", page.url());

  const html = await page.content();

  if (!html.includes('id="email"')) {

    console.log("LOGIN PAGE HTML:");
    console.log(html.substring(0, 5000));

    throw new Error(
      "Login page did not load correctly"
    );
  }

  const loginInput = page.locator("#email");
  const passwordInput = page.locator("#password");

  await loginInput.fill(
    "admin@corelabtech.local"
  );

  await passwordInput.fill(
    "Admin123!"
  );

  await page.locator(
    'button[type="submit"]'
  ).click();

  await page.waitForLoadState(
    "networkidle"
  );

  await expect(page).not.toHaveURL(
    /\/login/
  );
}