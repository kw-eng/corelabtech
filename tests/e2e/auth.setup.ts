import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers/login';
import fs from 'fs';

test('authenticate as admin', async ({ page }) => {
  await loginAsAdmin(page);

  fs.mkdirSync('tests/e2e/.auth', {
    recursive: true,
  });

  await page.context().storageState({
    path: 'tests/e2e/.auth/admin.json',
  });

  await expect(page).not.toHaveURL(/\/login/);
});
