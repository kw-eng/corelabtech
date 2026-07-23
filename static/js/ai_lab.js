// static/js/ai_lab.js

let aiTimelineChart = null
const AI_LAB_COLORS = {
    heartRate: "#2F9EED",
    pulse: "#F05A7E",
    spo2: "#F59F35",
    hrv: "#FFD05A",
    text: "rgba(226, 232, 240, 0.76)",
    grid: "rgba(148, 163, 184, 0.14)"
}

document.addEventListener("DOMContentLoaded", () => {
    loadSessions()
    loadLatestAI()
    setInterval(loadLatestAI, 15000)
})

async function parseJsonResponse(res, label){
    const text = await res.text()

    console.log(`${label} RAW RESPONSE:`, text)

    try{
        return JSON.parse(text)
    }catch(e){
        console.error(`${label} non-JSON response:`, text)
        return {
            status: "error",
            error: `${label} returned HTML/non-JSON`,
            raw: text
        }
    }
}

function escapeHtml(value){
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;")
}

function pickMetric(features, ...keys){
    for(const key of keys){
        const value = features[key]

        if(value !== undefined && value !== null && value !== ""){
            return value
        }
    }

    return null
}

function formatMetric(value, unit = ""){
    if(value === undefined || value === null || value === ""){
        return `<span class="muted-value">Not available</span>`
    }

    const suffix = unit ? ` <span class="metric-unit">${unit}</span>` : ""

    return `${escapeHtml(value)}${suffix}`
}

function formatScore(data){
    const value =
        data.score ??
        data.overall_score

    if(value === undefined || value === null || value === ""){
        return `<span class="muted-value">Pending</span>`
    }

    return `${escapeHtml(value)}<span class="metric-unit">/100</span>`
}

function riskLabel(data){
    const score =
        data.score ??
        data.overall_score

    return data.risk_level || (
        score >= 90
            ? "Low"
            : score >= 70
                ? "Moderate"
                : "High"
    )
}

function riskClass(label){
    const normalized = String(label || "").toLowerCase()

    if(normalized.includes("high")) return "status-high"
    if(normalized.includes("moderate")) return "status-moderate"

    return "status-low"
}

function renderFindingList(items, fallback, className = ""){
    const cleanItems =
        Array.isArray(items)
            ? items.filter(Boolean)
            : []

    if(!cleanItems.length){
        return `<div class="empty-state">${escapeHtml(fallback)}</div>`
    }

    return `
        <ul class="ai-finding-list ${className}">
            ${cleanItems
                .map(item => `<li>${escapeHtml(item)}</li>`)
                .join("")}
        </ul>
    `
}

function renderMetricRows(rows){
    return rows.map(row => `
        <div class="metric-row">
            <span>${escapeHtml(row.label)}</span>
            <strong>${formatMetric(row.value, row.unit)}</strong>
        </div>
    `).join("")
}

function formatShortTime(value){
    const date = new Date(value)

    if(Number.isNaN(date.getTime())){
        return value || ""
    }

    return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    })
}

async function loadSessions(){

    try{
        const res = await fetch("/api/sessions", {
            credentials: "same-origin"
        })

        const data = await parseJsonResponse(res, "AI LAB LOAD SESSIONS")

        const sessions =
            Array.isArray(data)
                ? data
                : Array.isArray(data.sessions)
                    ? data.sessions
                    : []

        const tbody = document.getElementById("sessionsBody")
        const sessionCount = document.getElementById("sessionCount")

        if(sessionCount){
            sessionCount.textContent = `${sessions.length} sessions`
        }

        if(!tbody){
            console.error("sessionsBody not found")
            return
        }

        tbody.innerHTML = ""

        if(!sessions.length){
            tbody.innerHTML = `
                <tr>
                    <td colspan="6">No completed sessions</td>
                </tr>
            `
            return
        }

        sessions.forEach(s => {
            const completedLabel =
                s.completed
                    ? `<span class="status-pill status-low">Completed</span>`
                    : `<span class="status-pill status-moderate">Open</span>`

            tbody.innerHTML += `
                <tr>
                    <td>
                        <input
                            type="checkbox"
                            class="session-checkbox"
                            value="${s.session_id}"
                        >
                    </td>

                    <td class="session-id-cell">${escapeHtml(s.session_id || "-")}</td>
                    <td>${escapeHtml(s.user_id || "-")}</td>
                    <td>${escapeHtml(s.date || s.created_at || "-")}</td>
                    <td>${completedLabel}</td>

                    <td>
                        <button class="tiny-action" onclick="runAnalysis('${escapeHtml(s.session_id)}')">
                            AI
                        </button>
                    </td>
                </tr>
            `
        })

    }catch(err){
        console.error("loadSessions error:", err)
        alert("Cannot load sessions")
    }
}

async function loadLatestAI(){

    try{
        const res = await fetch("/api/ai_latest", {
            credentials: "same-origin"
        })

        if(!res.ok){
            return
        }

        const data = await parseJsonResponse(res, "AI LAB LATEST")

        if(data.error){
            return
        }

        const anomalyText =
            data.anomaly
                ? "YES - abnormal response detected"
                : "NO critical anomaly detected"

        const box = document.getElementById("telemetryBox")

        if(box){
            box.innerHTML = `
                <div class="live-score">
                    <strong>${formatScore(data)}</strong>
                    <span class="status-badge ${riskClass(riskLabel(data))}">
                        ${escapeHtml(riskLabel(data))} risk
                    </span>
                </div>
                <p>${escapeHtml(data.summary || anomalyText)}</p>
            `
        }

    }catch(err){
        console.error("loadLatestAI error:", err)
    }
}

function toggleAll(master){
    document
        .querySelectorAll(".session-checkbox")
        .forEach(cb => {
            cb.checked = master.checked
        })
}

async function runSelectedAnalysis(){

    const selected = []

    document
        .querySelectorAll(".session-checkbox:checked")
        .forEach(cb => selected.push(cb.value))

    if(selected.length === 0){
        alert("Select at least one session")
        return
    }

    if(selected.length === 1){
        await runAnalysis(selected[0])
        return
    }

    await runBatchAnalysis(selected)
}

async function runLatestSession(){

    const rows = document.querySelectorAll(".session-checkbox")

    if(rows.length === 0){
        alert("No sessions available")
        return
    }

    const latestSession = rows[0].value

    await runAnalysis(latestSession)
}

async function runAnalysis(sessionId){

    try{
        const summary = document.getElementById("ai-summary")

        if(summary){
            summary.innerText = "Running AI analysis..."
        }

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

        const data = await parseJsonResponse(res, "AI LAB RUN ANALYSIS")

        console.log("AI LAB RESPONSE:", data)

        if(!res.ok || data.error){
            alert(data.error || "AI analysis failed")
            return
        }

        const anomalyText =
            data.anomaly
                ? "YES - abnormal response detected"
                : "NO critical anomaly detected"

        document.getElementById("ai-summary").innerHTML =
            `<b>Summary:</b> ${data.summary || "-"}`

        document.getElementById("ai-score").innerHTML =
            `<b>Score:</b> ${data.score ?? "-"} / 100`

        document.getElementById("ai-anomaly").innerHTML =
            `<b>Anomaly:</b> ${anomalyText}`

        renderAIVisualization(data)

    }catch(err){
        console.error("runAnalysis error:", err)
        alert("AI analysis crashed")
    }
}

async function runBatchAnalysis(sessionIds){

    const results = []

    for(const sessionId of sessionIds){

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

            const data = await parseJsonResponse(res, "AI LAB BATCH ANALYSIS")

            if(res.ok && !data.error){
                results.push(data)
            }

        }catch(err){
            console.error("Batch session failed:", sessionId, err)
        }
    }

    if(results.length === 0){
        alert("No sessions analyzed")
        return
    }

    renderBatchVisualization(results)
}

function renderAIVisualization(data){

    const container = document.getElementById("chartsContainer")

    if(!container){
        return
    }

    const features = data.features || {}

    const timeline =
        Array.isArray(data.timeline)
            ? data.timeline
            : []

    const anomalyDetected =
        data.anomaly ??
        data.anomaly_detected

    const anomalyText =
        anomalyDetected
            ? "YES - abnormal response detected"
            : "NO critical anomaly detected"

    const warnings =
        Array.isArray(data.reasons)
            ? data.reasons
            : []

    const positives =
        Array.isArray(data.positive_findings)
            ? data.positive_findings
            : []

    const label = riskLabel(data)
    const keyFinding =
        data.summary ||
        warnings[0] ||
        positives[0] ||
        "No critical rule-based finding was detected."
    const dataQuality =
        data.data_quality_score ??
        features.data_quality_score

    container.innerHTML = `
        <section class="ai-report">
            <div class="ai-report-header">
                <div>
                    <h3>AI Session Summary</h3>
                    <p>${escapeHtml(data.score_type || "Research risk score")}</p>
                </div>
                <span class="status-badge ${riskClass(label)}">
                    ${escapeHtml(label)} risk
                </span>
            </div>

            <div class="ai-kpi-grid">
                <div class="ai-kpi-card">
                    <span>Risk score</span>
                    <strong>${formatScore(data)}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>Anomaly status</span>
                    <strong>${escapeHtml(anomalyText)}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>Data quality</span>
                    <strong>${formatMetric(dataQuality, "/100")}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>Timeline samples</span>
                    <strong>${formatMetric(timeline.length)}</strong>
                </div>
            </div>

            <div class="ai-summary-grid">
                <div class="ai-summary-card ai-summary-card-wide">
                    <h4>Key Finding</h4>
                    <p>${escapeHtml(keyFinding)}</p>
                </div>

                <div class="ai-summary-card">
                    <h4>Warnings</h4>
                    ${renderFindingList(
                        warnings,
                        "No rule-based warning detected.",
                        warnings.length ? "warning-list" : ""
                    )}
                </div>

                <div class="ai-summary-card">
                    <h4>Positive Findings</h4>
                    ${renderFindingList(
                        positives,
                        "No additional positive findings."
                    )}
                </div>

                <div class="ai-summary-card">
                    <h4>Signal Quality</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            {
                                label: "Total samples",
                                value: pickMetric(features, "samples_total")
                            },
                            {
                                label: "Synchronized samples",
                                value: pickMetric(features, "samples_synchronized")
                            },
                            {
                                label: "Match rate",
                                value: pickMetric(features, "match_rate"),
                                unit: "%"
                            },
                            {
                                label: "Timeline samples",
                                value: timeline.length
                            }
                        ])}
                    </div>
                </div>

                <div class="ai-summary-card">
                    <h4>Physiology Metrics</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            {
                                label: "Average SpO2",
                                value: pickMetric(features, "avg_spo2", "avg_csv_spo2"),
                                unit: "%"
                            },
                            {
                                label: "SpO2 range",
                                value: (
                                    pickMetric(features, "min_spo2") !== null &&
                                    pickMetric(features, "max_spo2") !== null
                                )
                                    ? `${pickMetric(features, "min_spo2")}-${pickMetric(features, "max_spo2")}`
                                    : null,
                                unit: "%"
                            },
                            {
                                label: "Average pulse",
                                value: pickMetric(features, "avg_pulse", "avg_csv_pulse"),
                                unit: "bpm"
                            },
                            {
                                label: "Pulse range",
                                value: (
                                    pickMetric(features, "min_pulse", "min_csv_pulse") !== null &&
                                    pickMetric(features, "max_pulse", "max_csv_pulse") !== null
                                )
                                    ? `${pickMetric(features, "min_pulse", "min_csv_pulse")}-${pickMetric(features, "max_pulse", "max_csv_pulse")}`
                                    : null,
                                unit: "bpm"
                            },
                            {
                                label: "Average HR",
                                value: pickMetric(features, "avg_heart_rate", "avg_fit_hr"),
                                unit: "bpm"
                            },
                            {
                                label: "Average HRV",
                                value: pickMetric(features, "avg_hrv"),
                                unit: "ms"
                            }
                        ])}
                    </div>
                </div>

                <div class="ai-summary-card">
                    <h4>Rule Reference</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            { label: "Low risk", value: "90-100" },
                            { label: "Moderate risk", value: "70-89" },
                            { label: "High risk", value: "below 70" },
                            { label: "SpO2 warning", value: "below 94%" },
                            { label: "HRV warning", value: "below 30 ms" }
                        ])}
                    </div>
                </div>
            </div>

            <p class="ai-disclaimer">
                ${escapeHtml(data.medical_disclaimer || "Research-only score. Not a medical diagnosis.")}
            </p>
        </section>

        <div class="ai-chart-panel">
            <h3>AI Timeline</h3>
            <canvas id="aiTimelineChart"></canvas>
            <div id="aiTimelineStatus"></div>
        </div>
    `

    renderTimelineChart(timeline)
}

function renderTimelineChart(timeline){

    const status = document.getElementById("aiTimelineStatus")

    if(!timeline || timeline.length === 0){

        if(status){
            status.innerHTML = `
                <div class="warning-box">
                    No timeline data available for chart.
                </div>
            `
        }

        return
    }

    const canvas = document.getElementById("aiTimelineChart")

    if(!canvas){
        return
    }

    if(typeof Chart === "undefined"){

        if(status){
            status.innerHTML = `
                <div class="warning-box">
                    Chart.js is not loaded.
                </div>
            `
        }

        return
    }

    const labels = timeline.map(r => r.timestamp || r.time || "")

    const spo2 =
        timeline.map(r =>
            r.spo2 !== undefined && r.spo2 !== null
                ? Number(r.spo2)
                : null
        )

    const pulse =
        timeline.map(r => {

            const value =
                r.pulse ??
                r.csv_pulse ??
                null

            if(value === null){
                return null
            }

            const n = Number(value)

            return n < 30 ? null : n
        })

    const hr =
        timeline.map(r => {

            const value =
                r.heart_rate ??
                r.hr ??
                null

            return value !== null ? Number(value) : null
        })

    const hrv =
        timeline.map(r => {

            const value =
                r.hrv ?? null

            return value !== null ? Number(value) : null
        })

    if(
        window.aiTimelineChart &&
        typeof window.aiTimelineChart.destroy === "function"
    ){
        window.aiTimelineChart.destroy()
    }

    window.aiTimelineChart = null

    window.aiTimelineChart = new Chart(canvas.getContext("2d"), {
        type: "line",

        data: {
            labels: labels,
            datasets: [
                {
                    label: "SpO2 from CSV",
                    data: spo2,
                    borderColor: AI_LAB_COLORS.spo2,
                    backgroundColor: AI_LAB_COLORS.spo2,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "ySpo2",
                    spanGaps: true
                },
                {
                    label: "Pulse from CSV",
                    data: pulse,
                    borderColor: AI_LAB_COLORS.pulse,
                    backgroundColor: AI_LAB_COLORS.pulse,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "yVitals",
                    spanGaps: true
                },
                {
                    label: "HR from FIT",
                    data: hr,
                    borderColor: AI_LAB_COLORS.heartRate,
                    backgroundColor: AI_LAB_COLORS.heartRate,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "yVitals",
                    spanGaps: true
                },
                {
                    label: "HRV from FIT",
                    data: hrv,
                    borderColor: AI_LAB_COLORS.hrv,
                    backgroundColor: AI_LAB_COLORS.hrv,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "yHrv",
                    spanGaps: true
                }
            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,

            interaction: {
                mode: "index",
                intersect: false
            },

            elements: {
                line: {
                    tension: 0.18
                },
                point: {
                    hoverRadius: 4,
                    hitRadius: 8
                }
            },

            plugins: {
                legend: {
                    labels: {
                        color: AI_LAB_COLORS.text,
                        usePointStyle: true,
                        pointStyle: "line"
                    }
                }
            },

            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: AI_LAB_COLORS.text,
                        maxTicksLimit: 9,
                        maxRotation: 0,
                        callback: (_value, index) => formatShortTime(labels[index])
                    }
                },
                yVitals: {
                    type: "linear",
                    position: "left",
                    suggestedMin: 40,
                    suggestedMax: 120,
                    title: {
                        display: true,
                        text: "HR / Pulse bpm",
                        color: AI_LAB_COLORS.text
                    },
                    ticks: {
                        color: AI_LAB_COLORS.text
                    },
                    grid: {
                        color: AI_LAB_COLORS.grid
                    }
                },
                ySpo2: {
                    type: "linear",
                    position: "right",
                    suggestedMin: 88,
                    suggestedMax: 100,
                    title: {
                        display: true,
                        text: "SpO2 %",
                        color: AI_LAB_COLORS.spo2
                    },
                    ticks: {
                        color: AI_LAB_COLORS.spo2
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                },
                yHrv: {
                    type: "linear",
                    position: "right",
                    suggestedMin: 0,
                    suggestedMax: 120,
                    title: {
                        display: true,
                        text: "HRV ms",
                        color: AI_LAB_COLORS.hrv
                    },
                    ticks: {
                        color: AI_LAB_COLORS.hrv
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    })

    if(status){
        status.innerHTML = `
            <div class="success-box">
                Timeline chart rendered. Samples: ${timeline.length}
            </div>
        `
    }
}

function renderBatchVisualization(results){

    const container = document.getElementById("chartsContainer")

    const labels = results.map(r => r.session_id)
    const scores = results.map(r => r.score ?? r.overall_score ?? null)
    const postSpo2 = results.map(r => r.post?.spo2 ?? null)

    container.innerHTML = `
        <div class="panel">
            <h3>Batch AI Summary</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr><td>Sessions analyzed</td><td>${results.length}</td></tr>
                    <tr><td>Average score</td><td>${avg(scores)} / 100</td></tr>
                    <tr><td>Anomalies</td><td>${results.filter(r => r.anomaly ?? r.anomaly_detected).length}</td></tr>
                </tbody>
            </table>
        </div>

        <div class="panel chart-box" style="height:380px; min-height:380px; position:relative;">
            <h3>Batch Score Trend</h3>
            <canvas id="batchChart" style="width:100%; height:320px;"></canvas>
        </div>
    `

    const canvas = document.getElementById("batchChart")

    if(!canvas || typeof Chart === "undefined"){
        return
    }

    new Chart(canvas.getContext("2d"), {
        type: "line",

        data: {
            labels: labels,
            datasets: [
                {
                    label: "AI Score",
                    data: scores,
                    borderWidth: 2
                },
                {
                    label: "POST SpO2",
                    data: postSpo2,
                    borderWidth: 2
                }
            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    })
}

function avg(values){

    const clean =
        values.filter(v => v !== null && v !== undefined)

    if(clean.length === 0){
        return "-"
    }

    const sum =
        clean.reduce((a, b) => a + Number(b), 0)

    return (sum / clean.length).toFixed(2)
}

window.loadSessions = loadSessions
window.loadLatestAI = loadLatestAI
window.toggleAll = toggleAll
window.runSelectedAnalysis = runSelectedAnalysis
window.runLatestSession = runLatestSession
window.runAnalysis = runAnalysis
