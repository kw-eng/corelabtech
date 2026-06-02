import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./helpers/login";

test("AI analysis contract works for latest saved session", async ({ page }) => {

  const sessionsResponse = await page.request.get("/api/sessions");

  expect(sessionsResponse.ok()).toBeTruthy();

  const sessionsBody = await sessionsResponse.json();

  expect(sessionsBody).toHaveProperty("status", "ok");
  expect(sessionsBody).toHaveProperty("sessions");
  expect(Array.isArray(sessionsBody.sessions)).toBeTruthy();
  expect(sessionsBody.sessions.length).toBeGreaterThan(0);

  const sessionId = sessionsBody.sessions[0].session_id;

  const response = await page.request.post("/api/run_analysis", {
    data: {
      session_id: sessionId
    }
  });

  expect(response.ok()).toBeTruthy();

  const body = await response.json();

  expect(body).toHaveProperty("status", "ok");
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