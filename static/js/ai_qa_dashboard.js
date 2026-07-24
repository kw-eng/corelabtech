// static/js/ai_qa_dashboard.js

let sessionsCache = []

function pretty(data){
    return JSON.stringify(data, null, 2)
}

function compactTimeline(timeline){
    if(!Array.isArray(timeline)){
        return timeline
    }

    return {
        omitted: true,
        total_samples: timeline.length,
        first_samples: timeline.slice(0, 3),
        last_samples: timeline.slice(-3)
    }
}

function compactReportValue(value){
    if(Array.isArray(value)){
        return value.length > 20
            ? {
                omitted: true,
                total_items: value.length,
                first_items: value.slice(0, 3),
                last_items: value.slice(-3)
            }
            : value
    }

    if(!value || typeof value !== "object"){
        return value
    }

    const compacted = {}

    Object.entries(value).forEach(([key, item]) => {
        compacted[key] =
            key === "timeline"
                ? compactTimeline(item)
                : compactReportValue(item)
    })

    return compacted
}

function selectedSessionId(){
    return document.getElementById("sessionSelect")?.value
}

function selectedSession(){
    const id = selectedSessionId()
    return sessionsCache.find(s => s.session_id === id)
}

function setReport(data){
    const report = document.getElementById("qaReport")

    if(report){
        report.innerText = pretty(compactReportValue(data))
    }
}

function statusLabel(pass){
    return pass ? "PASS" : "FAIL"
}

function anomalyText(value){
    return value
        ? "Yes - review session quality"
        : "NO critical session flag detected"
}

function riskLevelFromScore(score){
    if(typeof score !== "number"){
        return null
    }

    if(score >= 90){
        return "Low"
    }

    if(score >= 70){
        return "Moderate"
    }

    return "High"
}

function normalizeAnalysisContract(data){
    const score =
        typeof data.score === "number"
            ? data.score
            : typeof data.overall_score === "number"
                ? data.overall_score
                : null

    const anomaly =
        typeof data.anomaly === "boolean"
            ? data.anomaly
            : typeof data.anomaly_detected === "boolean"
                ? data.anomaly_detected
                : null

    const riskLevel =
        data.risk_level ||
        data.risk ||
        riskLevelFromScore(score)

    return {
        ...data,
        score,
        anomaly,
        risk_level: riskLevel
    }
}

async function parseJsonResponse(res, label){
    const text = await res.text()
    console.log(`${label} RAW RESPONSE:`, text)

    try{
        return JSON.parse(text)
    }catch(e){
        console.error(`${label} returned non-JSON:`, text)

        return {
            status: "error",
            error: `${label} returned HTML/non-JSON response`,
            raw: text
        }
    }
}

function renderQAScorecard(data){
    const normalized = normalizeAnalysisContract(data)
    const score = normalized.score ?? 100
    const risk = normalized.risk_level || "-"
    const box = document.getElementById("qaScorecard")

    if(!box){
        return
    }

    box.innerHTML = `
        <div class="qa-grid">
            <div class="qa-card">
                <h3>AI QA Score</h3>
                <div class="qa-kpi">${score}/100</div>
                <div class="qa-muted">Research validation score</div>
            </div>

            <div class="qa-card">
                <h3>Risk Level</h3>
                <div class="qa-kpi">${risk}</div>
                <div class="qa-muted">Based on current AI rules</div>
            </div>

            <div class="qa-card">
                <h3>Session Flag</h3>
                <div class="qa-kpi">${normalized.anomaly ? "YES" : "NO"}</div>
                <div class="qa-muted">${anomalyText(normalized.anomaly)}</div>
            </div>

            <div class="qa-card">
                <h3>Timeline</h3>
                <div class="qa-kpi">
                    ${Array.isArray(normalized.timeline) ? normalized.timeline.length : 0}
                </div>
                <div class="qa-muted">samples validated</div>
            </div>
        </div>
    `
}

function renderPipelineSteps(data){
    const box = document.getElementById("qaPipelineSteps")

    if(!box){
        return
    }

    const normalized = normalizeAnalysisContract(data)
    const checks = [
        { label: "Session selected", pass: !!normalized.session_id },
        { label: "AI score returned", pass: typeof normalized.score === "number" },
        { label: "Risk level available", pass: !!normalized.risk_level },
        { label: "Session flag returned", pass: typeof normalized.anomaly === "boolean" },
        { label: "Features package returned", pass: !!normalized.features },
        { label: "Timeline returned", pass: Array.isArray(normalized.timeline) },
        { label: "Medical disclaimer returned", pass: !!normalized.medical_disclaimer }
    ]

    box.innerHTML = `
        <div class="qa-pipeline">
            ${
                checks.map(c => `
                    <div class="qa-step ${c.pass ? "pass" : "fail"}">
                        ${statusLabel(c.pass)} - ${c.label}
                    </div>
                `).join("")
            }
        </div>
    `
}

function renderGherkin(data){
    const box = document.getElementById("gherkinPreview")

    if(!box){
        return
    }

    const sessionId = data.session_id || selectedSessionId() || "selected-session"

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

function renderPlaywrightPreview(data){
    const box = document.getElementById("playwrightPreview")

    if(!box){
        return
    }

    const sessionId = data.session_id || selectedSessionId() || "SESSION_ID"

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

  expect(['completed', 'ok']).toContain(body.status);
  expect(typeof (body.score ?? body.overall_score)).toBe('number');
  expect(typeof (body.anomaly ?? body.anomaly_detected)).toBe('boolean');
  expect(body).toHaveProperty('features');
  expect(Array.isArray(body.timeline)).toBeTruthy();
  expect(body).toHaveProperty('medical_disclaimer');
});
`
}

async function loadSessions(){
    try{
        const res = await fetch("/api/sessions", {
            credentials: "same-origin"
        })
        const data = await parseJsonResponse(res, "SESSIONS")

        sessionsCache = Array.isArray(data)
            ? data
            : Array.isArray(data.sessions)
                ? data.sessions
                : []

        const select = document.getElementById("sessionSelect")

        if(!select){
            return
        }

        select.innerHTML = ""

        if(sessionsCache.length === 0){
            select.innerHTML = `<option value="">No sessions available</option>`
            return
        }

        sessionsCache.forEach(s => {
            select.innerHTML += `
                <option value="${s.session_id}">
                    ${s.session_id} | ${s.user_id || s.subject_id || "-"} | ${s.date || "-"}
                </option>
            `
        })
    }catch(err){
        console.error("loadSessions error:", err)
        setReport({
            status: "error",
            error: String(err)
        })
    }
}

async function runAITest(){
    const sessionId = selectedSessionId()

    if(!sessionId){
        alert("Select session")
        return
    }

    const box = document.getElementById("aiTestResult")
    box.innerHTML = `<div class="qa-step warn">Running AI validation...</div>`

    try{
        const res = await fetch("/api/run_analysis", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        })
        const data = await parseJsonResponse(res, "AI VALIDATION")

        if(!res.ok || data.error){
            box.innerHTML = `
                <div class="qa-step fail">
                    FAIL - AI validation failed: ${data.error || res.status}
                </div>
            `
            setReport(data)
            return
        }

        box.innerHTML = `
            <div class="qa-step pass">
                PASS - AI validation completed for session ${sessionId}
            </div>
        `

        renderQAScorecard(data)
        renderPipelineSteps(data)
        renderGherkin(data)
        renderPlaywrightPreview(data)
        setReport(data)
    }catch(err){
        console.error("runAITest error:", err)
        box.innerHTML = `
            <div class="qa-step fail">
                FAIL - AI validation crashed. Check browser console.
            </div>
        `
    }
}

async function runUserTrend(){
    const session = selectedSession()

    if(!session || !session.user_id){
        alert("Selected session has no user_id")
        return
    }

    try{
        const res = await fetch(`/api/user_trends/${session.user_id}`, {
            credentials: "same-origin"
        })
        const data = await parseJsonResponse(res, "USER TREND")

        document.getElementById("aiTestResult").innerHTML = `
            <div class="${res.ok ? "qa-step pass" : "qa-step fail"}">
                ${statusLabel(res.ok)} - User trend analysis completed
                <br><br>
                <b>User:</b> ${data.user_id || session.user_id}
                <br>
                <b>Records:</b> ${data.records ?? "-"}
                <br>
                <b>Trend:</b> telemetry timeline loaded
            </div>
        `

        setReport(data)
    }catch(err){
        console.error("runUserTrend error:", err)
        document.getElementById("aiTestResult").innerHTML = `
            <div class="qa-step fail">
                FAIL - User trend crashed. Check browser console.
            </div>
        `
    }
}

async function runFullSuite(){
    const status = document.getElementById("fullSuiteStatus")

    if(!status){
        return
    }

    status.innerHTML = `<div class="qa-step warn">Running Playwright QA...</div>`

    try{
        const res = await fetch("/api/qa/run_playwright", {
            method: "POST",
            credentials: "same-origin"
        })
        const data = await parseJsonResponse(res, "PLAYWRIGHT")
        const passed =
            res.ok &&
            data.status === "success" &&
            Number(data.returncode) === 0

        const stdout = data.stdout || ""
        const stderr = data.stderr || ""
        const passedMatch = stdout.match(/(\d+)\s+passed/)
        const failedMatch = stdout.match(/(\d+)\s+failed/)
        const passedCount = passedMatch ? passedMatch[1] : passed ? "all" : "-"
        const failedCount = passed ? "0" : failedMatch ? failedMatch[1] : "-"
        const reportPath =
            data.report_path ||
            data.report ||
            "/admin/playwright-report/index.html"

        status.innerHTML = `
            <div class="qa-step ${passed ? "pass" : "fail"}">
                <b>${passed ? "PASS - Playwright QA passed" : "FAIL - Playwright QA failed"}</b>
                <br><br>
                <b>Passed tests:</b> ${passedCount}
                <br>
                <b>Failed tests:</b> ${failedCount}
                <br>
                <b>Return code:</b> ${data.returncode ?? "-"}
                <br>
                <b>Command:</b> ${data.command || "-"}
                <br><br>
                <b>Report:</b>
                <a href="${reportPath}" target="_blank">Open Playwright report</a>
                ${
                    passed
                        ? ""
                        : `
                            <br><br>
                            <b>Error output:</b>
                            <pre class="qa-code">${(stderr || stdout || data.error || "").slice(-3000)}</pre>
                        `
                }
            </div>
        `

        setReport(data)
    }catch(err){
        console.error("runFullSuite error:", err)
        status.innerHTML = `
            <div class="qa-step fail">
                FAIL - Playwright QA crashed. Check Flask terminal and browser console.
            </div>
        `
    }
}

async function runApiHealthCheck(){
    const checks = [
        "/api/sessions",
        "/api/ai_latest"
    ]

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
                <b>${r.endpoint}</b>: ${statusLabel(r.ok)} ${r.status}
            </div>
        `).join("")

        document.getElementById("apiStatus").innerHTML = `
            <div class="qa-step ${passed === results.length ? "pass" : "fail"}">
                <b>${passed === results.length ? "PASS - API Health passed" : "FAIL - API Health failed"}</b>
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
            <div class="qa-step fail">FAIL - API Health Check crashed.</div>
        `
    }
}

async function runAIContractTest(){
    const status = document.getElementById("uiStatus")
    const sessionId = selectedSessionId()

    if(!sessionId){
        alert("Select session")
        return
    }

    status.innerHTML = `<div class="qa-step warn">Running AI contract test...</div>`

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
        const data = await parseJsonResponse(res, "AI CONTRACT")
        const normalized = normalizeAnalysisContract(data)
        const checks = [
            {
                label: "status is completed or ok",
                pass: ["completed", "ok"].includes(data.status)
            },
            {
                label: "score is number",
                pass: typeof normalized.score === "number"
            },
            {
                label: "anomaly is boolean",
                pass: typeof normalized.anomaly === "boolean"
            },
            {
                label: "risk level available or derived",
                pass: !!normalized.risk_level
            },
            {
                label: "features exists",
                pass: !!normalized.features
            },
            {
                label: "timeline is array",
                pass: Array.isArray(normalized.timeline)
            },
            {
                label: "medical_disclaimer exists",
                pass: !!normalized.medical_disclaimer
            }
        ]
        const passed = checks.filter(c => c.pass).length
        const ok = res.ok && passed === checks.length
        const rows = checks.map(c => `
            <div>${statusLabel(c.pass)} - ${c.label}</div>
        `).join("")

        status.innerHTML = `
            <div class="qa-step ${ok ? "pass" : "fail"}">
                <b>${ok ? "PASS - AI Contract passed" : "FAIL - AI Contract failed"}</b>
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
            normalized_contract: {
                status: data.status,
                score: normalized.score,
                anomaly: normalized.anomaly,
                risk_level: normalized.risk_level,
                timeline_samples: Array.isArray(normalized.timeline)
                    ? normalized.timeline.length
                    : 0
            },
            response: data
        })
    }catch(err){
        console.error("runAIContractTest error:", err)
        status.innerHTML = `
            <div class="qa-step fail">FAIL - AI Contract Test crashed.</div>
        `
    }
}

async function generateTests(){
    const prompt = document.getElementById("aiPrompt").value.trim()
    const sessionId = selectedSessionId() || "selected-session"
    const data = {
        session_id: sessionId,
        score_type: "AI Research Risk Score"
    }

    renderGherkin(data)

    document.getElementById("generatedTests").innerText =
        prompt
            ? `Preview generated for prompt: "${prompt}".`
            : "Preview generated successfully."
}

async function loadDebugDB(){
    try{
        const res = await fetch("/debug/db", {
            credentials: "same-origin"
        })

        if(res.status === 404){
            document.getElementById("debugDbOutput").innerText =
                "Debug database diagnostics are disabled in this environment."
            return
        }

        const data = await parseJsonResponse(res, "DEBUG DB")

        document.getElementById("debugDbOutput").innerText = pretty(data)
    }catch(err){
        console.error("loadDebugDB error:", err)
        document.getElementById("debugDbOutput").innerText =
            "Debug DB failed. Check console."
    }
}

function toggleAll(){}

window.addEventListener("load", () => {
    loadSessions()
})
