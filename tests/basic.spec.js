const { test, expect } = require('@playwright/test')

test('homepage works', async ({ page }) => {

    await page.goto('http://127.0.0.1:5000')

    await expect(page).toHaveTitle(/CoreLabTech/i)
})