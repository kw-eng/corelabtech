import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers/login';

test('authenticate as admin', async ({ page }) => {
  await loginAsAdmin(page);

  await page.context().storageState({
    path: 'tests/e2e/.auth/admin.json',
  });

  await expect(page).not.toHaveURL(/\/login/);
});