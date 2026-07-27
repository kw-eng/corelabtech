import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

const RUN_ID = Date.now();
const CLIENT_ID = `E2E_WELLNESS_CLIENT_${RUN_ID}`;
const SESSION_ID = `${CLIENT_ID}_${RUN_ID}`;
const EXTENDED_SESSION_ID = `${CLIENT_ID}_EXTENDED_${RUN_ID}`;
const FIT_PATH = path.resolve(
  "files/fenix8/23664778759_ACTIVITY.fit",
);
const CSV_PATH = path.resolve(
  "files/checkme/Checkme O2 _20260720130928.csv",
);
let CHAMBER_ID = 0;
let PROTOCOL_ID_15 = 0;
let PROGRAM_ID = 0;
let ENROLLMENT_ID = 0;

test.describe.serial("Wellness client FIT/CSV session flow", () => {
  test.use({
    storageState: "tests/e2e/.auth/admin.json",
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage({
      storageState: "tests/e2e/.auth/admin.json",
    });

    await page.request.post("/api/delete_subject", {
      data: {
        user_id: CLIENT_ID,
      },
    });

    await page.close();
  });

  test("01 - loads the wellness physiology session", async ({ page }) => {
    await page.goto("/chamber");

    await expect(page.locator("h1")).toContainText(
      "Physiology Session",
    );
    await expect(page.getByText("Client Profile")).toBeVisible();
    await expect(page.locator("#wellness_consent")).toBeVisible();
    await expect(page.locator("#step_pre")).toHaveText("Check-in");
    await expect(page.locator("#step_during")).toHaveText("Session");
    await expect(page.locator("#step_post")).toHaveText("Recovery");
    await expect(page.locator("#protocol_plan_preview")).toContainText(
      "120 min total",
    );
    await expect(page.locator("#during_compression_min")).toHaveValue("15");
    await expect(page.locator("#during_exposure_min")).toHaveValue("90");
    await expect(page.locator("#during_decompression_min")).toHaveValue("15");

    const chambersResponse = await page.request.get("/api/chambers");
    const protocolsResponse = await page.request.get("/api/protocols");
    const programsResponse = await page.request.get("/api/programs");
    expect(chambersResponse.status()).toBe(200);
    expect(protocolsResponse.status()).toBe(200);
    expect(programsResponse.status()).toBe(200);

    const chambers = await chambersResponse.json();
    const protocols = await protocolsResponse.json();
    const programs = await programsResponse.json();
    CHAMBER_ID = Number(chambers[0]?.chamber_id);
    PROTOCOL_ID_15 = Number(
      protocols.find(
        (protocol: {code: string}) =>
          protocol.code === "WELLNESS_1_5",
      )?.protocol_id,
    );

    expect(CHAMBER_ID).toBeGreaterThan(0);
    expect(PROTOCOL_ID_15).toBeGreaterThan(0);
    PROGRAM_ID = Number(
      programs.find(
        (program: {code: string}) => program.code === "RECOVERY_20",
      )?.program_id,
    );
    expect(PROGRAM_ID).toBeGreaterThan(0);
    const protocol15 = protocols.find(
      (protocol: {code: string}) =>
        protocol.code === "WELLNESS_1_5",
    );
    expect(protocol15.planned_duration_min).toBe(120);
    expect(protocol15.compression_time_min).toBe(15);
    expect(protocol15.exposure_time_min).toBe(90);
    expect(protocol15.decompression_time_min).toBe(15);
    expect(
      protocols.some(
        (protocol: {code: string}) =>
          protocol.code === "WELLNESS_1_3",
      ),
    ).toBeTruthy();
  });

  test("02 - creates a dedicated wellness client", async ({ page }) => {
    const response = await page.request.post("/api/subjects", {
      data: {
        subject_id: CLIENT_ID,
        sex: "M",
        age: 35,
        weight: 80,
        notes: "Automated wellness pipeline client",
      },
    });

    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.user_id).toBe(CLIENT_ID);

    const enrollment = await page.request.post("/api/client-programs", {
      data: {
        client_id: CLIENT_ID,
        program_id: PROGRAM_ID,
      },
    });
    expect(enrollment.status()).toBe(201);
    const enrollmentBody = await enrollment.json();
    ENROLLMENT_ID = Number(enrollmentBody.enrollment_id);
    expect(ENROLLMENT_ID).toBeGreaterThan(0);
  });

  test("03 - imports real FIT as HR/HRV for the client", async ({ page }) => {
    expect(fs.existsSync(FIT_PATH)).toBeTruthy();

    const response = await page.request.post("/upload_fit", {
      multipart: {
        session_id: SESSION_ID,
        client_id: CLIENT_ID,
        file: {
          name: path.basename(FIT_PATH),
          mimeType: "application/octet-stream",
          buffer: fs.readFileSync(FIT_PATH),
        },
      },
    });

    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.status).toBe("fit_saved");
    expect(body.user_id).toBe(CLIENT_ID);
    expect(body.records).toBeGreaterThan(0);
  });

  test("04 - imports real SpO2/pulse CSV for the client", async ({ page }) => {
    expect(fs.existsSync(CSV_PATH)).toBeTruthy();

    const response = await page.request.post("/upload_csv", {
      multipart: {
        session_id: SESSION_ID,
        client_id: CLIENT_ID,
        file: {
          name: path.basename(CSV_PATH),
          mimeType: "text/csv",
          buffer: fs.readFileSync(CSV_PATH),
        },
      },
    });

    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.status).toBe("csv_saved");
    expect(body.user_id).toBe(CLIENT_ID);
    expect(body.records).toBeGreaterThan(0);
  });

  test("05 - synchronizes FIT and CSV under one client", async ({ page }) => {
    const response = await page.request.post("/api/during_merge", {
      data: {
        session_id: SESSION_ID,
        client_id: CLIENT_ID,
      },
    });

    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.status).toBe("ok");
    expect(body.mode).toBe("fit_csv");
    expect(body.user_id).toBe(CLIENT_ID);
    expect(body.merged_records).toBeGreaterThan(0);
    expect(body.match_rate).toBeGreaterThan(0);
  });

  test("06 - requires consent and saves PRE/DURING/POST", async ({ page }) => {
    const withoutConsent = await page.request.post(
      "/api/save_full_session",
      {
        data: {
          session_id: SESSION_ID,
          client_id: CLIENT_ID,
          pre: { spo2: 98, pulse: 60 },
          during: {},
          post: { spo2: 98, pulse: 62 },
        },
      },
    );
    expect(withoutConsent.status()).toBe(400);

    const response = await page.request.post(
      "/api/save_full_session",
      {
        data: {
          session_id: SESSION_ID,
          client_id: CLIENT_ID,
          pre: {
            saved: true,
            phase: "pre",
            spo2: 98,
            pulse: 60,
            check_in: {
              sleep_hours: 7.5,
              sleep_quality: "good",
              stress_level: "low",
              training_load_24h: "light",
              fatigue_level: "low",
              session_goal: "recovery",
            },
            wellness_consent: {
              accepted: true,
              recorded_at: new Date().toISOString(),
            },
          },
          during: {
            saved: true,
            phase: "during",
            chamber_id: CHAMBER_ID,
            protocol_id: PROTOCOL_ID_15,
            target_ata: 1.5,
            actual_ata: 1.5,
            pressure_input_value: 1.5,
            pressure_input_unit: "ata",
            pressure_ata: 1.5,
            compression_time_min: 15,
            exposure_time_min: 90,
            decompression_time_min: 15,
            total_duration_min: 120,
            execution_status: "as_planned",
            program_enrollment_id: ENROLLMENT_ID,
            chamber_temperature: 24,
            oxygen_flow_lpm: 5,
          },
          post: {
            saved: true,
            phase: "post",
            spo2: 98,
            pulse: 62,
            check_out: {
              energy_level: "higher",
              relaxation_level: "high",
              fatigue_level: "lower",
              discomfort: "none",
            },
          },
        },
      },
    );

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe("ok");
    expect(body.client_id).toBe(CLIENT_ID);
    expect(body.saved_count).toBe(1);

    const savedSession = await page.request.get(
      `/api/sessions/${encodeURIComponent(SESSION_ID)}`,
    );
    const savedSessionBody = await savedSession.json();
    expect(savedSessionBody.protocol_id).toBe(PROTOCOL_ID_15);
    expect(savedSessionBody.target_ata).toBe(1.5);
    expect(savedSessionBody.actual_ata).toBe(1.5);
    expect(savedSessionBody.compression_time_min).toBe(15);
    expect(savedSessionBody.exposure_time_min).toBe(90);
    expect(savedSessionBody.decompression_time_min).toBe(15);
    expect(savedSessionBody.total_duration_min).toBe(120);
    expect(savedSessionBody.execution_status).toBe("as_planned");
    expect(savedSessionBody.program_enrollment_id).toBe(ENROLLMENT_ID);
    expect(savedSessionBody.segments).toHaveLength(3);
  });

  test("07 - analyzes the canonical client and preserves legacy aliases", async ({ page }) => {
    const response = await page.request.post("/api/run_analysis", {
      data: {
        session_id: SESSION_ID,
      },
    });

    expect(response.status()).toBe(201);
    const body = await response.json();

    expect(body.client_id).toBe(CLIENT_ID);
    expect(body.score_type).toBe("Wellness Response");
    expect(typeof body.wellness_response_score).toBe("number");
    expect(typeof body.data_quality_score).toBe("number");
    expect(body).toHaveProperty("wellness_status");
    expect(body).toHaveProperty("wellness_disclaimer");

    // Backward-compatible API aliases remain available.
    expect(typeof body.score).toBe("number");
    expect(typeof body.anomaly).toBe("boolean");
    expect(body).toHaveProperty("risk_level");
  });

  test("08 - counts one unique session after repeated analysis", async ({ page }) => {
    const repeated = await page.request.post("/api/run_analysis", {
      data: {
        session_id: SESSION_ID,
      },
    });
    expect(repeated.status()).toBe(201);

    const response = await page.request.get(
      `/api/user_trends/${encodeURIComponent(CLIENT_ID)}`,
    );
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.user_id).toBe(CLIENT_ID);
    expect(body.records).toBe(1);
    expect(body.session_count).toBe(1);
    expect(body.timeline).toHaveLength(1);
    expect(body.protocol.protocol_id).toBe(PROTOCOL_ID_15);
  });

  test("09 - returns the real daily baseline and PDF", async ({ page }) => {
    const baselineResponse = await page.request.get(
      `/api/wellness/summary/${encodeURIComponent(CLIENT_ID)}`,
    );
    expect(baselineResponse.status()).toBe(200);

    const baseline = await baselineResponse.json();
    expect(baseline.user_id).toBe(CLIENT_ID);
    expect(baseline).toHaveProperty("baseline");
    expect(baseline).toHaveProperty("baseline_confidence");
    expect(baseline.unique_sessions_30d).toBe(1);

    const reportResponse = await page.request.get(
      `/report/${encodeURIComponent(SESSION_ID)}`,
    );
    expect(reportResponse.status()).toBe(200);
    expect(reportResponse.headers()["content-type"]).toContain(
      "application/pdf",
    );
  });

  test("10 - exports client data and records auditable actions", async ({ page }) => {
    const exportResponse = await page.request.get(
      `/api/clients/${encodeURIComponent(CLIENT_ID)}/export`,
    );
    expect(exportResponse.status()).toBe(200);
    expect(exportResponse.headers()["content-type"]).toContain(
      "application/zip",
    );
    expect((await exportResponse.body()).length).toBeGreaterThan(100);

    const auditResponse = await page.request.get(
      `/api/admin/audit-log?client_id=${encodeURIComponent(CLIENT_ID)}`,
    );
    expect(auditResponse.status()).toBe(200);
    const audit = await auditResponse.json();
    const actions = audit.events.map(
      (event: {action: string}) => event.action,
    );
    expect(actions).toContain("client.create");
    expect(actions).toContain("session.complete");
    expect(actions).toContain("session.analyze");
    expect(actions).toContain("client.export");
  });

  test("11 - records an extended modified session with air breaks", async ({ page }) => {
    const response = await page.request.post("/api/save_full_session", {
      data: {
        session_id: EXTENDED_SESSION_ID,
        client_id: CLIENT_ID,
        pre: {
          saved: true,
          wellness_consent: {
            accepted: true,
            recorded_at: new Date().toISOString(),
          },
        },
        during: {
          saved: true,
          chamber_id: CHAMBER_ID,
          protocol_id: PROTOCOL_ID_15,
          target_ata: 1.5,
          pressure_input_value: 1.5,
          pressure_input_unit: "ata",
          compression_time_min: 15,
          exposure_time_min: 140,
          decompression_time_min: 15,
          execution_status: "modified",
          deviation_reason: "Extended operator-approved wellness session",
          segments: [
            {phase: "compression", actual_duration_min: 15},
            {phase: "exposure", actual_duration_min: 60},
            {phase: "air_break", actual_duration_min: 5},
            {phase: "exposure", actual_duration_min: 60},
            {phase: "air_break", actual_duration_min: 5},
            {phase: "exposure", actual_duration_min: 20},
            {phase: "decompression", actual_duration_min: 15},
          ],
        },
        post: {saved: true},
      },
    });
    expect(response.status()).toBe(200);

    const saved = await page.request.get(
      `/api/sessions/${encodeURIComponent(EXTENDED_SESSION_ID)}`,
    );
    expect(saved.status()).toBe(200);
    const body = await saved.json();
    expect(body.execution_status).toBe("modified");
    expect(body.deviation_reason).toContain("operator-approved");
    expect(body.total_duration_min).toBe(180);
    expect(body.segments).toHaveLength(7);
    expect(
      body.segments.filter(
        (segment: {phase: string}) => segment.phase === "air_break",
      ),
    ).toHaveLength(2);
  });
});
