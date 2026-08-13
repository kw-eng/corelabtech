import { expect, test } from "@playwright/test";

const SESSION_ID = "E2E_CONTRACT_SESSION";
const locales = {
  en: {
    analyze: "Analyze Session",
    loadSession: "Load Session",
    loadSeries: "Load Series",
    sessionReport: "Generate Session Report",
    seriesReport: "Generate Series Report",
    sessionInsight: "Your Session Insight",
    seriesInsight: "Your Wellness Trend",
    sessionSuccess: "Session report generated successfully.",
    seriesSuccess: "Session series report generated successfully.",
    forbidden: ["Ograniczenia danych", "Podsumowanie", "Nie zarejestrowano", "Jakość danych", "Stabilny", "Sesje"],
  },
  pl: {
    analyze: "Analizuj sesję",
    loadSession: "Załaduj sesję",
    loadSeries: "Załaduj serię",
    sessionReport: "Generuj raport sesji",
    seriesReport: "Generuj raport serii",
    sessionInsight: "Wnioski z Twojej sesji",
    seriesInsight: "Twój trend wellness",
    sessionSuccess: "Raport sesji został wygenerowany.",
    seriesSuccess: "Raport serii sesji został wygenerowany.",
    forbidden: ["Only a small number", "Session Summary AI", "Versioned deterministic summary", "sensor_alignment_warning", "heart_rate_bpm", "hrv_rmssd_ms", "spo2_percent"],
  },
} as const;

const rawCodes = ["sensor_alignment_warning", "heart_rate_bpm", "hrv_rmssd_ms", "spo2_percent"];

test.describe("Research customer dashboard acceptance", () => {
  for (const [locale, copy] of Object.entries(locales) as Array<[keyof typeof locales, (typeof locales)[keyof typeof locales]]>) {
    test(`${locale.toUpperCase()} renders localized session and series insight workflows`, async ({ page }, testInfo) => {
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });

      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto(`/research?lang=${locale}`);
      await expect.poll(
        () => page.locator("#sessionSelect option").evaluateAll(
          (options, sessionId) => options.some((option) => option.value === sessionId),
          SESSION_ID,
        ),
      ).toBe(true);
      await page.locator("#sessionSelect").selectOption(SESSION_ID);
      await page.screenshot({ path: testInfo.outputPath(`${locale}-research-initial-1440.png`), fullPage: true });

      await page.getByRole("button", { name: copy.analyze, exact: true }).click();
      await page.getByRole("button", { name: copy.loadSession, exact: true }).click();
      const sessionInsight = page.locator("#ai .mission-customer-insight");
      await expect(sessionInsight).toBeVisible();
      await expect(sessionInsight).toContainText(copy.sessionInsight);
      await expect(page.locator("#sessionWorkflowState [data-state='analyzed']")).toHaveClass(/is-complete/);

      const sessionText = (await sessionInsight.innerText()).toLowerCase();
      for (const forbidden of [...copy.forbidden, ...rawCodes]) {
        expect(sessionText).not.toContain(forbidden.toLowerCase());
      }

      await page.setViewportSize({ width: 768, height: 1000 });
      const sessionDownload = page.waitForEvent("download");
      await page.getByRole("button", { name: copy.sessionReport, exact: true }).click();
      const sessionFile = await sessionDownload;
      expect(sessionFile.suggestedFilename()).toMatch(new RegExp(`corelabtech_session_${SESSION_ID}_.*\\.pdf`, "i"));
      await sessionFile.saveAs(testInfo.outputPath(`${locale}-session-report.pdf`));
      await expect(page.locator("#missionNotice")).toContainText(copy.sessionSuccess);
      await page.screenshot({ path: testInfo.outputPath(`${locale}-research-session-768.png`), fullPage: true });

      await page.getByRole("button", { name: copy.loadSeries, exact: true }).click();
      const seriesInsight = page.locator("#trendBox .mission-customer-insight");
      await expect(seriesInsight).toBeVisible();
      await expect(seriesInsight).toContainText(copy.seriesInsight);
      const seriesText = (await seriesInsight.innerText()).toLowerCase();
      for (const forbidden of [...copy.forbidden, ...rawCodes]) {
        expect(seriesText).not.toContain(forbidden.toLowerCase());
      }

      await page.setViewportSize({ width: 390, height: 844 });
      const seriesDownload = page.waitForEvent("download");
      await page.getByRole("button", { name: copy.seriesReport, exact: true }).click();
      const seriesFile = await seriesDownload;
      expect(seriesFile.suggestedFilename()).toMatch(/corelabtech_series_E2E_CONTRACT_USER_last-25_.*\.pdf/i);
      await seriesFile.saveAs(testInfo.outputPath(`${locale}-series-report.pdf`));
      await expect(page.locator("#missionNotice")).toContainText(copy.seriesSuccess);
      await page.screenshot({ path: testInfo.outputPath(`${locale}-research-series-success-390.png`), fullPage: true });

      expect(consoleErrors).toEqual([]);
    });
  }
});
