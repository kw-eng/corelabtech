// static/js/ai_lab.js

let aiTimelineChart = null

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
            tbody.innerHTML += `
                <tr>
                    <td>
                        <input
                            type="checkbox"
                            class="session-checkbox"
                            value="${s.session_id}"
                        >
                    </td>

                    <td>${s.session_id || "-"}</td>
                    <td>${s.user_id || "-"}</td>
                    <td>${s.date || "-"}</td>
                    <td>${s.completed ? "YES" : "NO"}</td>

                    <td>
                        <button onclick="runAnalysis('${s.session_id}')">
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
                <b>AI Score:</b> ${data.score ?? "-"} / 100 |
                <b>Risk:</b> ${data.risk_level ?? "-"} |
                <b>Anomaly:</b> ${anomalyText}
                <br>
                ${data.summary || ""}
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

    const anomalyText =
        data.anomaly
            ? "YES - abnormal response detected"
            : "NO critical anomaly detected"

    const warnings =
        data.reasons && data.reasons.length
            ? data.reasons.join("<br>")
            : "No rule-based warning detected"

    const positives =
        data.positive_findings && data.positive_findings.length
            ? data.positive_findings.join("<br>")
            : "No additional positive findings"

    container.innerHTML = `
        <div class="panel">
            <h3>AI Session Summary</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr>
                        <td><b>Score type</b></td>
                        <td>${data.score_type || "AI Research Risk Score"}</td>
                    </tr>
                    <tr>
                        <td><b>Score</b></td>
                        <td>${data.score ?? "-"} / 100</td>
                    </tr>
                    <tr>
                        <td><b>Score reference</b></td>
                        <td>
                            90-100 = Low risk / stable session<br>
                            70-89 = Moderate warning / observe session<br>
                            below 70 = High risk / review required
                        </td>
                    </tr>
                    <tr>
                        <td><b>Risk level</b></td>
                        <td>${data.risk_level || "-"}</td>
                    </tr>
                    <tr>
                        <td><b>Anomaly</b></td>
                        <td>${anomalyText}</td>
                    </tr>
                    <tr>
                        <td><b>AI warnings</b></td>
                        <td>${warnings}</td>
                    </tr>
                    <tr>
                        <td><b>Positive findings</b></td>
                        <td>${positives}</td>
                    </tr>
                    <tr>
                        <td><b>Disclaimer</b></td>
                        <td>${data.medical_disclaimer || "Research-only score. Not a medical diagnosis."}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="panel">
            <h3>Physiology Metrics</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr><td>FIT samples</td><td>${features.fit_samples ?? "-"}</td></tr>
                    <tr><td>CSV samples</td><td>${features.csv_samples ?? "-"}</td></tr>
                    <tr><td>Avg SpO2 from CSV</td><td>${features.avg_csv_spo2 ?? "-"} %</td></tr>
                    <tr><td>Min SpO2 from CSV</td><td>${features.min_spo2 ?? "-"} %</td></tr>
                    <tr><td>Max SpO2 from CSV</td><td>${features.max_spo2 ?? "-"} %</td></tr>
                    <tr><td>Avg Pulse from CSV</td><td>${features.avg_csv_pulse ?? "-"} bpm</td></tr>
                    <tr><td>Max Pulse from CSV</td><td>${features.max_csv_pulse ?? "-"} bpm</td></tr>
                    <tr><td>Avg HR from FIT</td><td>${features.avg_fit_hr ?? "-"} bpm</td></tr>
                    <tr><td>Max HR from FIT</td><td>${features.max_fit_hr ?? "-"} bpm</td></tr>
                    <tr><td>Avg HRV from FIT</td><td>${features.avg_hrv ?? "-"} ms</td></tr>
                </tbody>
            </table>
        </div>

        <div class="panel ai-chart-panel">
            <h3>AI Timeline</h3>
            <canvas id="aiTimelineChart" style="width:100%; height:320px;"></canvas>
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
                    borderWidth: 2,
                    spanGaps: true
                },
                {
                    label: "Pulse from CSV",
                    data: pulse,
                    borderWidth: 2,
                    spanGaps: true
                },
                {
                    label: "HR from FIT",
                    data: hr,
                    borderWidth: 2,
                    spanGaps: true
                },
                {
                    label: "HRV from FIT",
                    data: hrv,
                    borderWidth: 2,
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

            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 10
                    }
                },
                y: {
                    beginAtZero: false
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
    const scores = results.map(r => r.score ?? null)
    const postSpo2 = results.map(r => r.post?.spo2 ?? null)

    container.innerHTML = `
        <div class="panel">
            <h3>Batch AI Summary</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr><td>Sessions analyzed</td><td>${results.length}</td></tr>
                    <tr><td>Average score</td><td>${avg(scores)} / 100</td></tr>
                    <tr><td>Anomalies</td><td>${results.filter(r => r.anomaly).length}</td></tr>
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