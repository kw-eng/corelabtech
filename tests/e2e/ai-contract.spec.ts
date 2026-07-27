import { test, expect } from "@playwright/test";

test("AI analysis contract works for latest saved session", async ({ page }) => {

  await page.goto("/ai-qa-lab");

  const sessionsResponse = await page.request.get("/api/sessions");

  expect(sessionsResponse.ok()).toBeTruthy();

  const sessionsBody = await sessionsResponse.json();

  console.log(
  "SESSION IDS:",
  sessionsBody.sessions.map(
    (s: { session_id: string }) => s.session_id
  )
);

  expect(sessionsBody).toHaveProperty("status", "ok");
  expect(sessionsBody).toHaveProperty("sessions");
  expect(Array.isArray(sessionsBody.sessions)).toBeTruthy();
  expect(sessionsBody.sessions.length).toBeGreaterThan(0);

  const contractSession = sessionsBody.sessions.find(
  (session: { session_id: string }) =>
    session.session_id === "E2E_CONTRACT_SESSION"
);

expect(contractSession).toBeTruthy();

const sessionId = contractSession.session_id;

const response = await page.request.post("/api/run_analysis", {
  data: {
    session_id: sessionId
  }
});

const raw = await response.text();

console.log("AI CONTRACT SESSION:", sessionId);
console.log("AI CONTRACT STATUS:", response.status());
console.log("AI CONTRACT BODY:", raw);

expect(response.ok()).toBeTruthy();
expect([200, 201]).toContain(response.status());

const body = JSON.parse(raw);

  expect(["ok", "completed"]).toContain(body.status);
  expect(body).toHaveProperty("session_id");
  expect(body).toHaveProperty("score");
  expect(body).toHaveProperty("risk_level");
  expect(body).toHaveProperty("anomaly");
  expect(body).toHaveProperty("features");
  expect(body).toHaveProperty("timeline");

  expect(typeof body.score).toBe("number");
  expect(typeof body.anomaly).toBe("boolean");
  expect(Array.isArray(body.timeline)).toBeTruthy();
});
