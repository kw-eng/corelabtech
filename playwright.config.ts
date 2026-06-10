import dotenv from "dotenv";
import { defineConfig, devices } from "@playwright/test";

dotenv.config({
  path: process.env.ENV_FILE || ".env.local",
});

export default defineConfig({

  workers: 1,

  testDir: './tests/e2e',

  timeout: 60_000,

  expect: {
    timeout: 15_000,
  },

  fullyParallel: false,

  retries: 0,

  reporter: [
    ['list'],
    ['html', {
      outputFolder: 'playwright-report',
      open: 'never',
    }],
  ],

  outputDir: 'test-results',

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5000',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'tests/e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
    },
  ],
});