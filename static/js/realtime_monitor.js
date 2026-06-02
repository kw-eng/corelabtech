// static/js/realtime_monitor.js

let telemetryInterval = null

// ========================================
// PUSH TELEMETRY
// ========================================

async function pushTelemetry(payload) {

    try {

        const res = await fetch("/api/push_telemetry", {

            method: "POST",

            credentials: "same-origin",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify(payload)
        })

        if (!res.ok) {

            console.warn(
                "Telemetry push failed:",
                res.status
            )
        }

    } catch (err) {

        console.error(
            "Telemetry push error",
            err
        )
    }
}

// ========================================
// LOAD REALTIME AI / TELEMETRY
// ========================================

async function loadRealtimeTelemetry() {

    try {

        // ========================================
        // USE EXISTING BACKEND ENDPOINT
        // ========================================

        const res = await fetch("/api/ai_latest", {

            credentials: "same-origin"

        })

        // ========================================
        // HANDLE 404 / HTML ERRORS
        // ========================================

        if (!res.ok) {

            console.warn(
                "Realtime endpoint error:",
                res.status
            )

            return
        }

        // ========================================
        // VALIDATE JSON RESPONSE
        // ========================================

        const contentType =
            res.headers.get("content-type") || ""

        if (
            !contentType.includes("application/json")
        ) {

            console.warn(
                "Realtime endpoint returned non-JSON"
            )

            return
        }

        const data = await res.json()

        console.log(
            "REALTIME DATA:",
            data
        )

        updateTelemetryUI(data)

    } catch (err) {

        console.error(
            "Realtime telemetry error",
            err
        )
    }
}

// ========================================
// UPDATE UI
// ========================================

function updateTelemetryUI(data) {

    // ========================================
    // PROTECT AGAINST EMPTY RESPONSE
    // ========================================

    if (!data || typeof data !== "object") {

        console.warn(
            "Realtime telemetry received invalid payload"
        )

        return
    }

    // ========================================
    // OPTIONAL LIVE METRIC ELEMENTS
    // ========================================

    const spo2 =
        document.getElementById("rt_spo2")

    const pulse =
        document.getElementById("rt_pulse")

    const hrv =
        document.getElementById("rt_hrv")

    const ata =
        document.getElementById("rt_ata")

    // ========================================
    // REALTIME AI SCORE PANEL
    // ========================================

    const liveScore =
        document.getElementById("liveScore")

    // ========================================
    // SIMPLE METRICS
    // ========================================

    if (spo2) {

        spo2.innerText =
            data.features?.avg_csv_spo2 ?? "-"
    }

    if (pulse) {

        pulse.innerText =
            data.features?.avg_csv_pulse ?? "-"
    }

    if (hrv) {

        hrv.innerText =
            data.features?.avg_hrv ?? "-"
    }

    if (ata) {

        ata.innerText =
            data.features?.pressure_ata ?? "-"
    }

    // ========================================
    // AI SCORE PANEL
    // ========================================

    if (liveScore) {

        const anomalyLabel =
            data.anomaly
                ? "YES - review required"
                : "NO critical anomaly"

        const riskLevel =
            data.score >= 90
                ? "Low"
                : data.score >= 70
                    ? "Moderate"
                    : "High"

        liveScore.innerHTML = `

            <div class="info-box">

                <h2>
                    AI Score:
                    ${data.score ?? "-"}
                </h2>

                <div>
                    <b>Risk:</b>
                    ${riskLevel}
                </div>

                <div>
                    <b>Anomaly:</b>
                    ${anomalyLabel}
                </div>

                <div style="margin-top:10px;">
                    ${data.summary || ""}
                </div>

            </div>
        `
    }
}

// ========================================
// START MONITOR
// ========================================

function startRealtimeMonitor() {

    if (telemetryInterval) {

        clearInterval(
            telemetryInterval
        )
    }

    // ========================================
    // INITIAL LOAD
    // ========================================

    loadRealtimeTelemetry()

    // ========================================
    // SAFE POLLING INTERVAL
    // ========================================

    telemetryInterval = setInterval(() => {

        loadRealtimeTelemetry()

    }, 15000)
}

// ========================================
// STOP MONITOR
// ========================================

function stopRealtimeMonitor() {

    if (telemetryInterval) {

        clearInterval(
            telemetryInterval
        )

        telemetryInterval = null
    }
}

// ========================================
// AUTO START
// ========================================

window.addEventListener("load", () => {

    startRealtimeMonitor()

})

// ========================================
// CLEANUP ON PAGE EXIT
// ========================================

window.addEventListener("beforeunload", () => {

    stopRealtimeMonitor()

})