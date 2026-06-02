import { test, expect } from '@playwright/test';

const USER_ID = 'E2E_DEMO_USER';
const SESSION_ID = `E2E_DEMO_${Date.now()}`;

test.describe.serial('Chamber HBOT pipeline - demo QA flow', () => {


test.use({
  storageState: "tests/e2e/.auth/admin.json",
});
test.afterAll(async ({ browser }) => {
  const page = await browser.newPage({
    storageState: "tests/e2e/.auth/admin.json",
  });

  await page.request.post('/api/delete_sessions', {
    data: {
      sessions: [SESSION_ID],
    },
  });

  await page.close();
});

  test('01 - should load Chamber Testing page', async ({ page }) => {
    await page.goto('/chamber');

    await expect(page.locator('h1')).toContainText('HBOT Testing Session');
  });

  test('02 - should return saved sessions list', async ({ page }) => {
    const res = await page.request.get('/api/sessions');

    expect(res.status()).toBe(200);

    const body = await res.json();

    expect(body).toHaveProperty('status', 'ok');
    expect(body).toHaveProperty('sessions');
    expect(Array.isArray(body.sessions)).toBeTruthy();
  });

  test('03 - should upload CSV telemetry for demo session', async ({ page }) => {
    const csv = [
      'timestamp,pulse,spo2',
      '2025-11-24T18:00:35,88,98',
      '2025-11-24T18:00:36,89,98',
      '2025-11-24T18:00:37,90,98',
      '2025-11-24T18:00:38,91,99',
      '2025-11-24T18:00:39,92,98',
    ].join('\n');

    const res = await page.request.post('/upload_csv', {
      multipart: {
        session_id: SESSION_ID,
        file: {
          name: 'demo_spo2_pulse.csv',
          mimeType: 'text/csv',
          buffer: Buffer.from(csv),
        },
      },
    });

    expect(res.status()).toBe(200);

    const body = await res.json();

    expect(body.status).toBe('csv_saved');
    expect(body.records).toBeGreaterThan(0);
    expect(body.session_id).toBe(SESSION_ID);
  });

  test('04 - should merge telemetry timeline', async ({ page }) => {
    const res = await page.request.post('/api/during_merge', {
      data: {
        session_id: SESSION_ID,
      },
    });

    expect(res.status()).toBe(200);

    const body = await res.json();

    expect(body.status).toBe('ok');
    // expect(body.saved_count).toBeGreaterThan(0);
    expect(body.mode).toBe('csv_only');
    expect(Array.isArray(body.merged)).toBeTruthy();
    expect(body.merged.length).toBeGreaterThan(0);
  });

test('05 - should save full PRE DURING POST session', async ({ page }) => {
  const mergeRes = await page.request.post('/api/during_merge', {
    data: {
      session_id: SESSION_ID,
    },
  });

  const mergeRaw = await mergeRes.text();

  console.log('MERGE STATUS:', mergeRes.status());
  console.log('MERGE RAW:', mergeRaw);

  expect(mergeRes.status()).toBe(200);

  const mergeBody = JSON.parse(mergeRaw);

  expect(mergeBody.status).toBe('ok');
  expect(Array.isArray(mergeBody.merged)).toBeTruthy();
  expect(mergeBody.merged.length).toBeGreaterThan(0);

  const payload = {
    session_id: SESSION_ID,
    user_id: USER_ID,

    pre: {
      saved: true,
      phase: 'pre',
      spo2: 98,
      pulse: 60,
    },

    during: {
      saved: true,
      phase: 'during',
      pressure_kpa: 50,
      pressure_ata: 1.5,
      chamber_temperature: 24,
      body_temperature: 36.6,
      humidity: 45,
      oxygen_flow_lpm: 5,
      oxygen_mask_percent: 93,
      merged: mergeBody.merged || [],
    },

    post: {
      saved: true,
      phase: 'post',
      spo2: 97,
      pulse: 70,
    },
  };

  const res = await page.request.post('/api/save_full_session', {
    data: payload,
  });

  const raw = await res.text();

  console.log('SAVE FULL STATUS:', res.status());
  console.log('SAVE FULL RAW:', raw);

  expect(res.status()).toBe(200);

  const body = JSON.parse(raw);

  expect(body.status).toBe('ok');
  expect(body.session_id).toBe(SESSION_ID);
  expect(body.saved_count).toBeGreaterThan(0);
  expect(body.features).toHaveProperty('avg_csv_spo2');
  expect(body.features).toHaveProperty('avg_csv_pulse');
});

test('06 - should run AI analysis for demo session', async ({ page }) => {
  const res = await page.request.post('/api/run_analysis', {
    data: {
      session_id: SESSION_ID,
    },
  });

  const raw = await res.text();

  console.log('RUN ANALYSIS STATUS:', res.status());
  console.log('RUN ANALYSIS RAW:', raw);

  expect(res.status()).toBe(200);

  const body = JSON.parse(raw);

  expect(body.status).toBe('ok');
  expect(body.session_id).toBe(SESSION_ID);

  expect(typeof body.score).toBe('number');
  expect(typeof body.anomaly).toBe('boolean');

  expect(body).toHaveProperty('risk_level');
  expect(body).toHaveProperty('summary');
  expect(body).toHaveProperty('features');
  expect(body).toHaveProperty('timeline');
  expect(body).toHaveProperty('medical_disclaimer');

  expect(Array.isArray(body.timeline)).toBeTruthy();
  expect(body.timeline.length).toBeGreaterThan(0);
});

  test('07 - should return user trend for demo user', async ({ page }) => {
    const res = await page.request.get(`/api/user_trends/${USER_ID}`);

    expect(res.status()).toBe(200);

    const body = await res.json();

    expect(body.user_id).toBe(USER_ID);
    expect(body).toHaveProperty('records');
    expect(body).toHaveProperty('timeline');
    expect(Array.isArray(body.timeline)).toBeTruthy();
  });

});