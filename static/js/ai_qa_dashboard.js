// =========================================================
// static/js/ai_qa_dashboard.js
// FINAL PRODUCTION VERSION
// =========================================================

let sessionsCache = []

// =========================================================
// HELPERS
// =========================================================

function pretty(data){
    return JSON.stringify(data, null, 2)
}

function selectedSessionId(){
    return document.getElementById("sessionSelect")?.value
}

function selectedSession(){

    const id =
        selectedSessionId()

    return sessionsCache.find(
        s => s.session_id === id
    )
}

function anomalyText(value){

    return value
        ? "YES - abnormal response detected"
        : "NO critical anomaly detected"
}

function setReport(data){

    const report =
        document.getElementById("qaReport")

    if(report){
        report.innerText =
            pretty(data)
    }
}

// =========================================================
// SAFE JSON PARSER
// =========================================================

async function parseJsonResponse(res, label){

    const text =
        await res.text()

    console.log(`${label} RAW RESPONSE:`, text)

    try{

        return JSON.parse(text)

    }catch(e){

        console.error(
            `${label} returned non-JSON:`,
            text
        )

        return {
            status: "error",
            error: `${label} returned HTML/non-JSON response`,
            raw: text
        }
    }
}

// =========================================================
// QA SCORECARD
// =========================================================

function renderQAScorecard(data){

    const score =
        data.score ?? 100

    const risk =
        data.risk_level || (
            score >= 90
                ? "Low"
                : score >= 70
                    ? "Moderate"
                    : "High"
        )

    const box =
        document.getElementById("qaScorecard")

    if(!box){
        return
    }

    box.innerHTML = `
        <div class="qa-grid">

            <div class="qa-card">
                <h3>AI QA Score</h3>
                <div class="qa-kpi">${score}/100</div>
                <div class="qa-muted">
                    Research validation score
                </div>
            </div>

            <div class="qa-card">
                <h3>Risk Level</h3>
                <div class="qa-kpi">${risk}</div>
                <div class="qa-muted">
                    Based on current AI rules
                </div>
            </div>

            <div class="qa-card">
                <h3>Anomaly</h3>
                <div class="qa-kpi">
                    ${data.anomaly ? "YES" : "NO"}
                </div>
                <div class="qa-muted">
                    ${anomalyText(data.anomaly)}
                </div>
            </div>

            <div class="qa-card">
                <h3>Timeline</h3>
                <div class="qa-kpi">
                    ${
                        Array.isArray(data.timeline)
                            ? data.timeline.length
                            : 0
                    }
                </div>
                <div class="qa-muted">
                    samples validated
                </div>
            </div>

        </div>
    `
}

// =========================================================
// PIPELINE STEPS
// =========================================================

function renderPipelineSteps(data){

    const box =
        document.getElementById("qaPipelineSteps")

    if(!box){
        return
    }

    const checks = [

        {
            label: "Session selected",
            pass: !!data.session_id
        },

        {
            label: "AI score returned",
            pass: typeof data.score === "number"
        },

        {
            label: "Risk level returned",
            pass: !!data.risk_level
        },

        {
            label: "Anomaly flag returned",
            pass: typeof data.anomaly === "boolean"
        },

        {
            label: "Features package returned",
            pass: !!data.features
        },

        {
            label: "Timeline returned",
            pass: Array.isArray(data.timeline)
        },

        {
            label: "Medical disclaimer returned",
            pass: !!data.medical_disclaimer
        }
    ]

    box.innerHTML = `
        <div class="qa-pipeline">

            ${
                checks.map(c => `

                    <div class="qa-step ${c.pass ? "pass" : "fail"}">
                        ${c.pass ? "✓" : "✕"} ${c.label}
                    </div>

                `).join("")
            }

        </div>
    `
}

// =========================================================
// GHERKIN
// =========================================================

function renderGherkin(data){

    const box =
        document.getElementById("gherkinPreview")

    if(!box){
        return
    }

    const sessionId =
        data.session_id ||
        selectedSessionId() ||
        "selected-session"

    box.innerText = `
Feature: HBOT AI physiology validation

  Background:
    Given a completed HBOT session exists
    And the session id is "${sessionId}"
    And PRE, DURING and POST phase data are available

  Scenario: Normal oxygenation response
    Given DURING SpO2 remains above 95%
    When the AI analysis endpoint is executed
    Then anomaly should be false

  Scenario: High warning oxygen desaturation
    Given POST SpO2 is below 90%
    When the AI analysis endpoint is executed
    Then anomaly should be true

  Scenario: Research-only disclaimer
    Given an AI analysis result is returned
    Then the result should include a research-only disclaimer
`
}

// =========================================================
// PLAYWRIGHT PREVIEW
// =========================================================

function renderPlaywrightPreview(data){

    const box =
        document.getElementById("playwrightPreview")

    if(!box){
        return
    }

    const sessionId =
        data.session_id ||
        selectedSessionId() ||
        "SESSION_ID"

    box.innerText = `
import { test, expect } from '@playwright/test';

test('validate HBOT AI session contract', async ({ request }) => {

  const res = await request.post('/api/run_analysis', {
    data: {
      session_id: '${sessionId}'
    }
  });

  expect(res.status()).toBe(200);

  const body = await res.json();

  expect(typeof body.score).toBe('number');
  expect(typeof body.anomaly).toBe('boolean');
  expect(body).toHaveProperty('risk_level');
  expect(body).toHaveProperty('features');
  expect(Array.isArray(body.timeline)).toBeTruthy();
  expect(body).toHaveProperty('medical_disclaimer');

});
`
}

// =========================================================
// LOAD SESSIONS
// =========================================================

async function loadSessions(){

    try{

        const res =
            await fetch("/api/sessions", {
                credentials: "same-origin"
            })

        const data =
            await parseJsonResponse(
                res,
                "SESSIONS"
            )

        sessionsCache =
            Array.isArray(data)
                ? data
                : Array.isArray(data.sessions)
                    ? data.sessions
                    : []

        const select =
            document.getElementById("sessionSelect")

        if(!select){
            return
        }

        select.innerHTML = ""

        if(sessionsCache.length === 0){

            select.innerHTML = `
                <option value="">
                    No sessions available
                </option>
            `

            return
        }

        sessionsCache.forEach(s => {

            select.innerHTML += `
                <option value="${s.session_id}">
                    ${s.session_id}
                    |
                    ${s.user_id || "-"}
                    |
                    ${s.date || "-"}
                </option>
            `
        })

    }catch(err){

        console.error(
            "loadSessions error:",
            err
        )

        setReport({
            status: "error",
            error: String(err)
        })
    }
}

// =========================================================
// RUN AI TEST
// =========================================================

async function runAITest(){

    const sessionId =
        selectedSessionId()

    if(!sessionId){

        alert("Select session")
        return
    }

    const box =
        document.getElementById("aiTestResult")

    box.innerHTML =
        "Running AI validation..."

    try{

        const res = await fetch(
            "/api/run_analysis",
            {
                method: "POST",

                credentials: "same-origin",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    session_id: sessionId
                })
            }
        )

        const data =
            await parseJsonResponse(
                res,
                "AI VALIDATION"
            )

        if(!res.ok || data.error){

            box.innerHTML = `
                <div class="qa-step fail">
                    AI validation failed:
                    ${data.error || res.status}
                </div>
            `

            setReport(data)
            return
        }

        box.innerHTML = `
            <div class="qa-step pass">
                ✓ AI validation completed
                for session ${sessionId}
            </div>
        `

        renderQAScorecard(data)
        renderPipelineSteps(data)
        renderGherkin(data)
        renderPlaywrightPreview(data)
        setReport(data)

    }catch(err){

        console.error(
            "runAITest error:",
            err
        )

        box.innerHTML = `
            <div class="qa-step fail">
                AI validation crashed.
                Check browser console.
            </div>
        `
    }
}

// =========================================================
// USER TREND
// =========================================================

async function runUserTrend(){

    const session =
        selectedSession()

    if(!session || !session.user_id){

        alert("Selected session has no user_id")
        return
    }

    try{

        const res =
            await fetch(
                `/api/user_trends/${session.user_id}`,
                {
                    credentials: "same-origin"
                }
            )

        const data =
            await parseJsonResponse(
                res,
                "USER TREND"
            )

        document.getElementById(
            "aiTestResult"
        ).innerHTML = `
            <div class="${res.ok ? "qa-step pass" : "qa-step fail"}">

                ${res.ok ? "✓" : "✕"}
                User trend analysis completed

                <br>

                User:
                ${data.user_id || session.user_id}

                <br>

                Records:
                ${data.records ?? "-"}

                <br>

                Trend:
                telemetry timeline loaded

            </div>
        `

        setReport(data)

    }catch(err){

        console.error(
            "runUserTrend error:",
            err
        )

        document.getElementById(
            "aiTestResult"
        ).innerHTML = `
            <div class="qa-step fail">
                User trend crashed.
                Check browser console.
            </div>
        `
    }
}

// =========================================================
// PLAYWRIGHT QA
// =========================================================

async function runFullSuite(){

    const status =
        document.getElementById("fullSuiteStatus")

    status.innerHTML =
        "Running Playwright QA..."

    try{

        const res =
            await fetch(
                "/api/run_playwright",
                {
                    method: "POST",
                    credentials: "same-origin"
                }
            )

        const data =
            await parseJsonResponse(
                res,
                "PLAYWRIGHT"
            )

        console.log("PLAYWRIGHT RESPONSE:", data)

        const passed =
            res.ok &&
            data.status === "success" &&
            Number(data.returncode) === 0

        const stdout =
            data.stdout || ""

        const stderr =
            data.stderr || ""

        const passedMatch =
            stdout.match(/(\d+)\s+passed/)

        const failedMatch =
            stdout.match(/(\d+)\s+failed/)

        const passedCount =
            passedMatch
                ? passedMatch[1]
                : passed
                    ? "all"
                    : "-"

        const failedCount =
            passed
                ? "0"
                : failedMatch
                    ? failedMatch[1]
                    : "-"

        const reportPath =
            data.report_path ||
            data.report ||
            "/admin/playwright-report/index.html"

        status.innerHTML = `
            <div class="qa-step ${passed ? "pass" : "fail"}">

                <b>
                    ${
                        passed
                            ? "✓ Playwright QA PASSED"
                            : "✕ Playwright QA FAILED"
                    }
                </b>

                <br><br>

                <b>Passed tests:</b>
                ${passedCount}

                <br>

                <b>Failed tests:</b>
                ${failedCount}

                <br>

                <b>Return code:</b>
                ${data.returncode ?? "-"}

                <br>

                <b>Command:</b>
                ${data.command || "-"}

                <br><br>

                <b>Report:</b>
                <a href="${reportPath}" target="_blank">
                   Open Playwright Report
                </a>

                ${
                    passed
                        ? ""
                        : `
                            <br><br>
                            <b>Error output:</b>
                            <pre class="qa-code">${
                                (stderr || stdout || data.error || "")
                                    .slice(-3000)
                            }</pre>
                        `
                }

            </div>
        `

        setReport(data)

    }catch(err){

        console.error(
            "runFullSuite error:",
            err
        )

        status.innerHTML = `
            <div class="qa-step fail">
                ✕ Playwright QA crashed.
                Check Flask terminal and browser console.
            </div>
        `
    }
}
// =========================================================
// API HEALTH CHECK
// =========================================================

async function runApiHealthCheck(){

const checks = [
    "/api/sessions",
    "/api/ai_latest"
]

const isAdmin =
    document.body.dataset.role === "admin"

if(isAdmin){
    checks.push("/debug/db")
}

    const results = []

    try{

        for(const url of checks){

            try{

                const res = await fetch(url, {
                    credentials: "include"
                })

                results.push({
                    endpoint: url,
                    status: res.status,
                    ok: res.ok
                })

            }catch(err){

                results.push({
                    endpoint: url,
                    status: "-",
                    ok: false,
                    error: String(err)
                })
            }
        }

        const passed = results.filter(r => r.ok).length

        const rows = results.map(r => `
            <div>
                <b>${r.endpoint}</b>:
                ${r.ok ? "✓" : "✕"}
                ${r.status}
            </div>
        `).join("")

        document.getElementById("apiStatus").innerHTML = `
            <div class="qa-step ${passed === results.length ? "pass" : "fail"}">
                <b>${passed === results.length ? "✓ API Health PASSED" : "✕ API Health FAILED"}</b>
                <br><br>
                Quick backend smoke test. No HTML report.
                <br><br>
                ${passed}/${results.length} passed
                <br><br>
                ${rows}
            </div>
        `

        setReport(results)

    }catch(err){

        console.error("runApiHealthCheck error:", err)

        document.getElementById("apiStatus").innerHTML = `
            <div class="qa-step fail">
                API Health Check crashed.
            </div>
        `
    }
}

// =========================================================
// AI CONTRACT
// =========================================================

async function runAIContractTest(){

    const status = document.getElementById("uiStatus")
    const sessionId = selectedSessionId()

    if(!sessionId){
        alert("Select session")
        return
    }

    status.innerHTML = "Running AI contract test..."

    try{

        const res = await fetch("/api/run_analysis", {
            method: "POST",
            credentials: "include",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        })

        const data = await parseJsonResponse(
            res,
            "AI CONTRACT"
        )

        const checks = [
            {
                label: "status = ok",
                pass: data.status === "ok"
            },
            {
                label: "score is number",
                pass: typeof data.score === "number"
            },
            {
                label: "anomaly is boolean",
                pass: typeof data.anomaly === "boolean"
            },
            {
                label: "risk_level exists",
                pass: !!data.risk_level
            },
            {
                label: "features exists",
                pass: !!data.features
            },
            {
                label: "timeline is array",
                pass: Array.isArray(data.timeline)
            },
            {
                label: "medical_disclaimer exists",
                pass: !!data.medical_disclaimer
            }
        ]

        const passed = checks.filter(c => c.pass).length
        const ok = res.ok && passed === checks.length

        const rows = checks.map(c => `
            <div>
                ${c.pass ? "✓" : "✕"} ${c.label}
            </div>
        `).join("")

        status.innerHTML = `
            <div class="qa-step ${ok ? "pass" : "fail"}">
                <b>${ok ? "✓ AI Contract PASSED" : "✕ AI Contract FAILED"}</b>
                <br><br>
                Validates AI JSON contract. No HTML report.
                <br><br>
                <b>Session:</b> ${sessionId}
                <br>
                <b>Checks:</b> ${passed}/${checks.length}
                <br><br>
                ${rows}
            </div>
        `

        setReport({
            status: ok ? "passed" : "failed",
            session_id: sessionId,
            checks: checks,
            response: data
        })

    }catch(err){

        console.error("runAIContractTest error:", err)

        status.innerHTML = `
            <div class="qa-step fail">
                AI Contract Test crashed.
            </div>
        `
    }
}

// =========================================================
// GENERATED TESTS
// =========================================================

async function generateTests(){

    const prompt =
        document.getElementById("aiPrompt")
            .value
            .trim()

    const sessionId =
        selectedSessionId() ||
        "selected-session"

    const data = {
        session_id: sessionId,
        score_type: "AI Research Risk Score"
    }

    renderGherkin(data)

    document.getElementById(
        "generatedTests"
    ).innerText =
        prompt
            ? `Preview generated for prompt: "${prompt}".`
            : "Preview generated successfully."
}

// =========================================================
// DEBUG DB
// =========================================================

async function loadDebugDB(){

    try{

        const res =
            await fetch(
                "/debug/db",
                {
                    credentials: "same-origin"
                }
            )

        const data =
            await parseJsonResponse(
                res,
                "DEBUG DB"
            )

        document.getElementById(
            "debugDbOutput"
        ).innerText =
            pretty(data)

    }catch(err){

        console.error(
            "loadDebugDB error:",
            err
        )

        document.getElementById(
            "debugDbOutput"
        ).innerText =
            "Debug DB failed. Check console."
    }
}

// =========================================================
// TOGGLE
// =========================================================

function toggleAll(){}

// =========================================================
// INIT
// =========================================================

window.addEventListener("load", () => {
    loadSessions()
})