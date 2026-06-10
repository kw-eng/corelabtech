import { test, expect } from '@playwright/test';

test.describe('AI QA Lab - current pipeline', () => {

  // =====================================================
  // PAGE LOAD
  // =====================================================

  test('should load AI QA Lab page', async ({ page }) => {

    await page.goto('/ai-qa-lab');

    await expect(
      page.locator('h1')
    ).toContainText('AI QA Lab');
  });

  // =====================================================
  // SESSIONS API
  // =====================================================

  test('API health: sessions endpoint works', async ({ page }) => {

    const res = await page.request.get('/api/sessions');

    expect(res.status()).toBe(200);

    const raw = await res.text();

    console.log("SESSIONS RAW:", raw);

    expect(raw.startsWith("{")).toBeTruthy();

    const body = JSON.parse(raw);

    expect(body).toHaveProperty('status', 'ok');

    expect(body).toHaveProperty('sessions');

    expect(
      Array.isArray(body.sessions)
    ).toBeTruthy();
  });

  // =====================================================
  // AI LATEST
  // =====================================================

  test('API health: latest AI endpoint returns JSON', async ({ page }) => {

    const res = await page.request.get('/api/ai_latest');

    expect([200, 404]).toContain(
      res.status()
    );

    if (res.status() === 200) {

      const body = await res.json();

      expect(body).toBeTruthy();
    }
  });

  // =====================================================
  // UI ELEMENTS
  // =====================================================

  test('AI QA Lab should show session selector and QA buttons', async ({ page }) => {

    await page.goto('/ai-qa-lab');

    await expect(
      page.locator('#sessionSelect')
    ).toBeVisible();

    await expect(
      page.getByRole('button', { name: 'Run AI Validation' })
    ).toBeVisible();

    await expect(
      page.getByRole('button', { name: 'Run Playwright QA' })
    ).toBeVisible();
  });

});