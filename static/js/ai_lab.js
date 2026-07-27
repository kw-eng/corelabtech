// static/js/ai_lab.js

let aiTimelineChart = null
let aiLabSessionIndex = new Map()
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

function wellnessStatus(data){
    const features = data.features || {}
    const warnings = qualityWarnings(data, features)
    const quality = Number(data.data_quality_score ?? features.data_quality_score)

    if(warnings.length || (Number.isFinite(quality) && quality < 75)){
        return "data_quality_warning"
    }

    return (
        data.wellness_status ??
        data.result?.wellness_status ??
        (
            data.elevated_load
                ? "elevated_load"
                : data.data_quality_score < 60
                    ? "data_quality_warning"
                    : "baseline"
        )
    )
}

function wellnessLabel(status){
    const labels = {
        baseline: "Baseline",
        elevated_load: "Elevated load",
        recovery_trend: "Recovery trend",
        data_quality_warning: "Baseline, review data quality"
    }

    return labels[status] || status || "Not available"
}

function wellnessClass(status){
    if(status === "elevated_load") return "status-high"
    if(status === "data_quality_warning") return "status-moderate"
    return "status-low"
}

function confidenceLevel(data, features = {}){
    const warnings = qualityWarnings(data, features)
    const quality = Number(data.data_quality_score ?? features.data_quality_score)

    if(warnings.includes("missing_hrv_or_rr") || (Number.isFinite(quality) && quality < 70)){
        return {
            label: "Low confidence",
            className: "status-moderate",
            reason: "HRV/RR signal is incomplete or data quality requires review."
        }
    }

    if(warnings.length || (Number.isFinite(quality) && quality < 85)){
        return {
            label: "Medium confidence",
            className: "status-moderate",
            reason: "The session is usable, but signal quality should be reviewed."
        }
    }

    return {
        label: "High confidence",
        className: "status-low",
        reason: "Signals are complete enough for a stronger session interpretation."
    }
}

function qualityWarnings(data, features = {}){
    const result = data.result || {}
    const warnings =
        data.quality_warnings ??
        result.quality_warnings ??
        features.quality_warnings ??
        []

    return Array.isArray(warnings)
        ? warnings
        : []
}

function readableWarning(value){
    const labels = {
        sensor_alignment_warning: "Heart-rate sensors were not fully aligned",
        missing_hrv_or_rr: "HRV signal was not available for this session",
        missing_spo2: "SpO2 signal was not available for this session",
        low_match_rate: "Timeline synchronization quality was lower than expected",
        too_few_total_samples: "Not enough samples for a strong interpretation",
        too_few_synchronized_samples: "Too few synchronized samples for a strong interpretation"
    }

    return labels[value] || value
}

function clientInterpretation(data, features = {}){
    const warnings = qualityWarnings(data, features)
    const status = wellnessStatus(data)

    if(status === "data_quality_warning"){
        if(warnings.includes("missing_hrv_or_rr")){
            return "SpO2 and pulse can be reviewed, but HRV-based interpretation has low confidence because HRV/RR data is incomplete."
        }

        return "The session can be reviewed, but the interpretation should be treated as provisional because signal quality requires attention."
    }

    if(status === "elevated_load"){
        return "The session shows signs of elevated physiological load and should be reviewed in context."
    }

    if(status === "recovery_trend"){
        return "The session shows a positive recovery-oriented pattern compared with available signals."
    }

    return "The session appears stable within the available wellness signals."
}

function priorityAction(data, features = {}){
    const warnings = qualityWarnings(data, features)
    const status = wellnessStatus(data)

    if(warnings.includes("missing_hrv_or_rr")){
        return "Use this report for SpO2/pulse review and repeat the next session with HRV/RR capture enabled."
    }

    if(warnings.includes("sensor_alignment_warning")){
        return "Check sensor placement and timeline alignment before interpreting heart-rate differences."
    }

    if(status === "elevated_load"){
        return "Review session load, recovery response and recent baseline before the next protocol decision."
    }

    return "Continue collecting repeat sessions to strengthen the personal baseline."
}

function conciseSummary(text){
    const clean = String(text || "").trim()

    if(!clean){
        return "No session summary available yet."
    }

    const firstSentence = clean.match(/^.*?[.!?](\s|$)/)

    return firstSentence
        ? firstSentence[0].trim()
        : clean
}

function getSubjectId(data){
    const sessionId = data.session_id

    if(sessionId && aiLabSessionIndex.has(sessionId)){
        return aiLabSessionIndex.get(sessionId).user_id
    }

    return data.user_id || data.result?.user_id || null
}

function baselineReadiness(records, baseline = null){
    const count = Number(
        baseline?.sessions_count_30d ??
        records ??
        0
    )
    const quality = Number(baseline?.data_quality_score)

    if(count >= 14 && (!Number.isFinite(quality) || quality >= 70)){
        return {
            label: "Trend baseline ready",
            className: "status-low",
            text: "There is enough quality-controlled history for a useful rolling wellness trend.",
            count
        }
    }

    if(count >= 5){
        return {
            label: "Early trend forming",
            className: "status-moderate",
            text: "The system can compare sessions, but confidence will improve with more consistent data.",
            count
        }
    }

    return {
        label: "Collect more sessions",
        className: "status-moderate",
        text: "Use this as a session review. At least 5 consistent sessions are recommended for early trend coaching.",
        count
    }
}

function baselineDelta(current, reference){
    const currentValue = Number(current)
    const referenceValue = Number(reference)

    if(
        !Number.isFinite(currentValue) ||
        !Number.isFinite(referenceValue) ||
        referenceValue === 0
    ){
        return "comparison unavailable"
    }

    const delta =
        ((currentValue - referenceValue) / Math.abs(referenceValue)) * 100
    const prefix = delta > 0 ? "+" : ""

    return `${prefix}${delta.toFixed(1)}% vs baseline`
}

function coachTrendLabel(trend){
    const direction = String(trend?.trend_direction || "").toLowerCase()
    const records = Number(trend?.records || 0)

    if(records < 5){
        return "Insufficient history"
    }

    if(direction.includes("up") || direction.includes("improv")){
        return "Recovery markers improving"
    }

    if(direction.includes("down") || direction.includes("declin")){
        return "Recovery markers need review"
    }

    return "Stable trend"
}

function coachRecommendation(data, features = {}, trend = null){
    const warnings = qualityWarnings(data, features)
    const status = wellnessStatus(data)
    const records = Number(trend?.records || 0)
    const context = contextFeatures(data)

    if(records < 5){
        return "Continue collecting sessions before making strong protocol decisions. Keep measurement timing and sensor setup consistent."
    }

    if(warnings.includes("missing_hrv_or_rr")){
        return "Repeat the next session with HRV/RR capture enabled before using HRV-based recovery coaching."
    }

    if(context.poor_sleep){
        return "Sleep was limited or low quality. Treat today's session as recovery support and avoid over-interpreting HRV changes."
    }

    if(context.high_training_load){
        return "Recent hard training can elevate load markers. Compare the next session after a lighter day."
    }

    if(context.high_stress_or_fatigue){
        return "Reported stress or fatigue is high. Prioritize recovery and repeat baseline measurement tomorrow."
    }

    if(context.positive_subjective_response && status === "baseline"){
        return "Subjective recovery feedback is positive and physiology is stable. Continue the current protocol and monitor trend consistency."
    }

    if(status === "elevated_load"){
        return "Consider a lighter recovery day and compare the next session against baseline before increasing session frequency."
    }

    if(status === "data_quality_warning"){
        return "Review sensor quality first. If the next session is clean and markers stay stable, continue the current protocol."
    }

    return "Continue the current wellness protocol and watch whether HR, HRV and SpO2 remain stable across the next sessions."
}

function dailyContextMessage(){
    return "Sleep, training load, stress and rest-day context are not connected yet. Add a short daily check-in to unlock stronger coaching."
}

function sessionContext(data){
    return (
        data.session_context ||
        data.result?.session_context ||
        data.features?.session_context ||
        {}
    )
}

function contextFeatures(data){
    return (
        data.context_features ||
        data.result?.context_features ||
        data.features?.context_features ||
        {}
    )
}

function formatContextSummary(data){
    const context = sessionContext(data)
    const pre = context.pre_check_in || {}
    const post = context.post_check_out || {}

    if(!contextFeatures(data).has_daily_context){
        return dailyContextMessage()
    }

    const parts = []

    if(pre.sleep_hours || pre.sleep_quality){
        parts.push(`Sleep: ${pre.sleep_hours || "-"}h, ${pre.sleep_quality || "quality not set"}`)
    }

    if(pre.training_load_24h){
        parts.push(`Training: ${pre.training_load_24h}`)
    }

    if(pre.stress_level || pre.fatigue_level){
        parts.push(`Stress/fatigue: ${pre.stress_level || "-"} / ${pre.fatigue_level || "-"}`)
    }

    if(pre.session_goal){
        parts.push(`Goal: ${pre.session_goal}`)
    }

    if(post.energy_level || post.relaxation_level || post.discomfort){
        parts.push(`After: energy ${post.energy_level || "-"}, relaxation ${post.relaxation_level || "-"}, discomfort ${post.discomfort || "-"}`)
    }

    return parts.join(". ") || "Daily context recorded."
}

function renderCoachPanel(data, trend = null, wellness = null){
    const features = data.features || {}
    const baseline = wellness?.baseline || null
    const readiness = baselineReadiness(trend?.records, baseline)
    const confidence = confidenceLevel(data, features)
    const protocol =
        data.protocol ||
        data.result?.protocol ||
        trend?.protocol ||
        {}

    return `
        <div class="coach-card" id="coachPanel">
            <div class="coach-header">
                <div>
                    <span>Recovery Coach Insight</span>
                    <h3>${escapeHtml(coachTrendLabel(trend))}</h3>
                    <p>${escapeHtml(readiness.text)}</p>
                </div>
                <span class="status-badge ${readiness.className}">
                    ${escapeHtml(readiness.label)}
                </span>
            </div>

            <div class="coach-grid">
                <div>
                    <span>Protocol-matched trend</span>
                    <strong>${escapeHtml(protocol.name || "Protocol not recorded")}</strong>
                    <p>
                        Target ${formatMetric(protocol.target_ata, "ATA")}.
                        History excludes sessions using other protocols.
                    </p>
                </div>
                <div>
                    <span>Trend history</span>
                    <strong>${escapeHtml(readiness.count)} unique sessions</strong>
                    <p>${escapeHtml(trend?.trend_direction || "More sessions needed for direction.")}</p>
                </div>
                <div>
                    <span>Session confidence</span>
                    <strong>${escapeHtml(confidence.label)}</strong>
                    <p>${escapeHtml(confidence.reason)}</p>
                </div>
                <div>
                    <span>RMSSD baseline</span>
                    <strong>
                        7d ${formatMetric(baseline?.rmssd_7d, "ms")} /
                        14d ${formatMetric(baseline?.rmssd_14d, "ms")} /
                        30d ${formatMetric(baseline?.rmssd_30d, "ms")}
                    </strong>
                    <p>
                        Current ${formatMetric(pickMetric(features, "avg_hrv"), "ms")} ·
                        ${escapeHtml(baselineDelta(
                            pickMetric(features, "avg_hrv"),
                            baseline?.rmssd_30d
                        ))}
                    </p>
                </div>
                <div>
                    <span>HR and SpO2 baseline</span>
                    <strong>
                        HR ${formatMetric(baseline?.resting_hr_7d, "bpm")} ·
                        SpO2 ${formatMetric(baseline?.spo2_avg, "%")}
                    </strong>
                    <p>
                        Current HR ${formatMetric(pickMetric(features, "avg_heart_rate", "avg_fit_hr"), "bpm")}
                        (${escapeHtml(baselineDelta(
                            pickMetric(features, "avg_heart_rate", "avg_fit_hr"),
                            baseline?.resting_hr_7d
                        ))});
                        current SpO2 ${formatMetric(pickMetric(features, "avg_spo2", "avg_csv_spo2"), "%")}
                        (${escapeHtml(baselineDelta(
                            pickMetric(features, "avg_spo2", "avg_csv_spo2"),
                            baseline?.spo2_avg
                        ))}).
                    </p>
                </div>
                <div>
                    <span>Daily context</span>
                    <strong>${contextFeatures(data).has_daily_context ? "Check-in recorded" : "Not connected yet"}</strong>
                    <p>${escapeHtml(formatContextSummary(data))}</p>
                </div>
                <div>
                    <span>Coach recommendation</span>
                    <strong>Next step</strong>
                    <p>${escapeHtml(coachRecommendation(data, features, trend))}</p>
                </div>
            </div>
        </div>
    `
}

async function hydrateCoachPanel(data){
    const subjectId = getSubjectId(data)
    const panel = document.getElementById("coachPanel")

    if(!panel || !subjectId){
        return
    }

    try{
        const protocolId =
            data.protocol?.protocol_id ||
            data.result?.protocol?.protocol_id ||
            data.features?.session_context?.protocol_id
        const protocolQuery = protocolId
            ? `?protocol_id=${encodeURIComponent(protocolId)}`
            : ""
        const [trendRes, wellnessRes] = await Promise.all([
            fetch(`/api/user_trends/${encodeURIComponent(subjectId)}${protocolQuery}`, {
                credentials: "same-origin"
            }),
            fetch(`/api/wellness/summary/${encodeURIComponent(subjectId)}${protocolQuery}`, {
                credentials: "same-origin"
            })
        ])

        if(!trendRes.ok || !wellnessRes.ok){
            return
        }

        const trend = await parseJsonResponse(trendRes, "AI LAB USER TREND")
        const wellness = await parseJsonResponse(
            wellnessRes,
            "AI LAB WELLNESS BASELINE"
        )
        const readiness = baselineReadiness(
            trend?.records,
            wellness?.baseline
        )

        panel.outerHTML = renderCoachPanel(data, trend, wellness)

        const baselineConfidence =
            document.getElementById("baselineConfidenceValue")
        if(baselineConfidence){
            baselineConfidence.textContent = readiness.label
        }
    }catch(err){
        console.error("hydrateCoachPanel error:", err)
    }
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

        aiLabSessionIndex = new Map()

        sessions.forEach(s => {
            aiLabSessionIndex.set(s.session_id, s)

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
                            Review
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

        const status = wellnessStatus(data)
        const features = data.features || {}
        const confidence = confidenceLevel(data, features)

        const box = document.getElementById("telemetryBox")

        if(box){
            box.innerHTML = `
                <div class="live-score">
                    <strong>${formatScore(data)}</strong>
                    <span class="status-badge ${wellnessClass(status)}">
                        ${escapeHtml(wellnessLabel(status))}
                    </span>
                    <span class="status-badge ${confidence.className}">
                        ${escapeHtml(confidence.label)}
                    </span>
                </div>
                <p>${escapeHtml(conciseSummary(data.summary || "Latest wellness analysis"))}</p>
            `
        }

        hydrateCoachPanel(data)

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

        const status = wellnessStatus(data)

        document.getElementById("ai-summary").innerHTML =
            `<b>Summary:</b> ${escapeHtml(conciseSummary(data.summary))}`

        document.getElementById("ai-score").innerHTML =
            `<b>Wellness response:</b> ${data.score ?? "-"} / 100`

        document.getElementById("ai-anomaly").innerHTML =
            `<b>Wellness status:</b> ${wellnessLabel(status)}`

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

    const warnings =
        Array.isArray(data.reasons)
            ? data.reasons
            : []
    const signalWarnings = qualityWarnings(data, features)
        .map(readableWarning)

    const positives =
        Array.isArray(data.positive_findings)
            ? data.positive_findings
            : []

    const status = wellnessStatus(data)
    const confidence = confidenceLevel(data, features)
    const keyFinding =
        conciseSummary(data.summary) ||
        warnings[0] ||
        positives[0] ||
        "No elevated load was detected."
    const dataQuality =
        data.data_quality_score ??
        features.data_quality_score

    container.innerHTML = `
        <section class="ai-report">
            ${renderCoachPanel(data)}

            <div class="client-verdict-card">
                <div>
                    <span>Client-ready status</span>
                    <h3>${escapeHtml(wellnessLabel(status))}</h3>
                    <p>${escapeHtml(clientInterpretation(data, features))}</p>
                </div>
                <div class="client-verdict-side">
                    <span class="status-badge ${confidence.className}">
                        ${escapeHtml(confidence.label)}
                    </span>
                    <p>${escapeHtml(confidence.reason)}</p>
                </div>
            </div>

            <div class="ai-report-header">
                <div>
                    <h3>Session Wellness Summary</h3>
                    <p>${escapeHtml(data.score_type || "Wellness session score")}</p>
                </div>
                <span class="status-badge ${wellnessClass(status)}">
                    ${escapeHtml(wellnessLabel(status))}
                </span>
            </div>

            <div class="ai-kpi-grid">
                <div class="ai-kpi-card">
                    <span>Wellness response</span>
                    <strong>${formatScore(data)}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>Baseline confidence</span>
                    <strong id="baselineConfidenceValue">Loading history...</strong>
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
                    <h4>Plain-language interpretation</h4>
                    <p>${escapeHtml(keyFinding)}</p>
                </div>

                <div class="ai-summary-card ai-summary-card-wide action-card">
                    <h4>Recommended next step</h4>
                    <p>${escapeHtml(priorityAction(data, features))}</p>
                </div>

                <div class="ai-summary-card">
                    <h4>Data quality notes</h4>
                    ${renderFindingList(
                        signalWarnings,
                        "No data quality issue detected.",
                        signalWarnings.length ? "warning-list" : ""
                    )}
                </div>

                <div class="ai-summary-card">
                    <h4>Session findings</h4>
                    ${renderFindingList(
                        [...positives, ...warnings],
                        "No elevated load finding detected."
                    )}
                </div>

                <div class="ai-summary-card">
                    <h4>Signal quality</h4>
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
                    <h4>Physiology metrics</h4>
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
                    <h4>Status reference</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            { label: "Baseline", value: "stable session response" },
                            { label: "Elevated load", value: "SpO2 drop, high HR or low HRV" },
                            { label: "Recovery trend", value: "positive post-session response" },
                            { label: "Data quality warning", value: "missing signal or sensor mismatch" }
                        ])}
                    </div>
                </div>
            </div>

            <p class="ai-disclaimer">
                ${escapeHtml(data.wellness_disclaimer || data.medical_disclaimer || "Wellness insight only. Not a medical diagnosis.")}
            </p>
        </section>

        <div class="ai-chart-panel">
            <h3>Session Timeline</h3>
            <canvas id="aiTimelineChart"></canvas>
            <div id="aiTimelineStatus"></div>
        </div>
    `

    renderTimelineChart(timeline)
    hydrateCoachPanel(data)
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
                    label: "SpO2 from SpO2/pulse timeline",
                    data: spo2,
                    borderColor: AI_LAB_COLORS.spo2,
                    backgroundColor: AI_LAB_COLORS.spo2,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "ySpo2",
                    spanGaps: true
                },
                {
                    label: "Pulse from SpO2/pulse timeline",
                    data: pulse,
                    borderColor: AI_LAB_COLORS.pulse,
                    backgroundColor: AI_LAB_COLORS.pulse,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "yVitals",
                    spanGaps: true
                },
                {
                    label: "HR from HR/HRV timeline",
                    data: hr,
                    borderColor: AI_LAB_COLORS.heartRate,
                    backgroundColor: AI_LAB_COLORS.heartRate,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    yAxisID: "yVitals",
                    spanGaps: true
                },
                {
                    label: "HRV from HR/HRV timeline",
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
                    <tr><td>Average wellness response</td><td>${avg(scores)} / 100</td></tr>
                    <tr><td>Sessions recommended for review</td><td>${results.filter(r => r.anomaly ?? r.anomaly_detected).length}</td></tr>
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
                    label: "Wellness Response",
                    data: scores,
                    borderWidth: 2
                },
                {
                    label: "Recovery SpO2",
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
