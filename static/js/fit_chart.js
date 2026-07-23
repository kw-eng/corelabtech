// static/js/fit_chart.js

let fitChart = null
const FIT_CHART_TABLE_PREVIEW_LIMIT = 5000
const FIT_CHART_TABLE_RENDER_CHUNK_SIZE = 100
const CHART_COLORS = {
    heartRate: "#2F9EED",
    pulse: "#F05A7E",
    spo2: "#F59F35",
    hrv: "#FFD05A",
    grid: "rgba(148, 163, 184, 0.14)",
    text: "rgba(226, 232, 240, 0.76)"
}

function fitChartWaitForNextFrame() {
    return new Promise(resolve => {
        if (typeof requestAnimationFrame === "function") {
            requestAnimationFrame(resolve)
            return
        }

        setTimeout(resolve, 0)
    })
}

function fitChartDisplayValue(...values) {
    const value = values.find(item => (
        item !== undefined &&
        item !== null &&
        item !== ""
    ))

    return value === undefined ? "-" : value
}

function formatChartTime(value) {
    const date = new Date(value)

    if (Number.isNaN(date.getTime())) {
        return value || ""
    }

    return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    })
}

function toNumberOrNull(value) {
    if (value === undefined || value === null || value === "") {
        return null
    }

    const parsed = Number(value)

    return Number.isFinite(parsed) ? parsed : null
}

function buildTimelineDataset(rows, fields) {
    return rows.map(row => {
        const value = fields
            .map(field => row[field])
            .find(item => item !== undefined && item !== null && item !== "")

        return toNumberOrNull(value)
    })
}

function buildProfessionalChart(canvas, labels, datasets) {
    const ctx = canvas.getContext("2d")

    if (fitChart) {
        fitChart.destroy()
        fitChart = null
    }

    fitChart = new Chart(ctx, {
        type: "line",

        data: {
            labels,
            datasets
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,
            normalized: true,

            interaction: {
                mode: "index",
                intersect: false
            },

            animation: false,

            elements: {
                point: {
                    radius: 0,
                    hoverRadius: 4,
                    hitRadius: 8
                },
                line: {
                    tension: 0.18,
                    borderWidth: 1.8
                }
            },

            plugins: {
                legend: {
                    position: "top",
                    align: "center",
                    labels: {
                        color: CHART_COLORS.text,
                        boxWidth: 28,
                        boxHeight: 3,
                        padding: 18,
                        usePointStyle: true,
                        pointStyle: "line"
                    }
                },
                tooltip: {
                    backgroundColor: "rgba(15, 23, 42, 0.94)",
                    borderColor: "rgba(148, 163, 184, 0.28)",
                    borderWidth: 1,
                    titleColor: "#F8FAFC",
                    bodyColor: "#E2E8F0",
                    padding: 10,
                    callbacks: {
                        title: items => {
                            const rawLabel = items[0]?.label
                            const date = new Date(rawLabel)

                            if (Number.isNaN(date.getTime())) {
                                return rawLabel || ""
                            }

                            return date.toLocaleString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                                day: "2-digit",
                                month: "short"
                            })
                        }
                    }
                },
                decimation: {
                    enabled: true,
                    algorithm: "lttb",
                    samples: 900
                }
            },

            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: CHART_COLORS.text,
                        maxTicksLimit: 9,
                        maxRotation: 0,
                        autoSkip: true,
                        callback: (_value, index) => formatChartTime(labels[index])
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
                        color: CHART_COLORS.text
                    },
                    ticks: {
                        color: CHART_COLORS.text
                    },
                    grid: {
                        color: CHART_COLORS.grid,
                        drawBorder: false
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
                        color: CHART_COLORS.spo2
                    },
                    ticks: {
                        color: CHART_COLORS.spo2
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
                    offset: true,
                    title: {
                        display: true,
                        text: "HRV RMSSD ms",
                        color: CHART_COLORS.hrv
                    },
                    ticks: {
                        color: CHART_COLORS.hrv
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            }
        }
    })
}

async function fitChartRenderRowsChunked(tbody, rows, columns) {
    tbody.replaceChildren()

    for (
        let start = 0;
        start < rows.length;
        start += FIT_CHART_TABLE_RENDER_CHUNK_SIZE
    ) {
        const fragment =
            document.createDocumentFragment()

        rows
            .slice(start, start + FIT_CHART_TABLE_RENDER_CHUNK_SIZE)
            .forEach(row => {
                const tr =
                    document.createElement("tr")

                columns.forEach(getValue => {
                    const td =
                        document.createElement("td")

                    td.textContent = getValue(row)

                    tr.appendChild(td)
                })

                fragment.appendChild(tr)
            })

        tbody.appendChild(fragment)

        if (
            start + FIT_CHART_TABLE_RENDER_CHUNK_SIZE <
            rows.length
        ) {
            await fitChartWaitForNextFrame()
        }
    }
}

// ========================================
// LOAD MAIN FIT CHART
// ========================================

async function loadFitChart(session_id, importId = null) {

    try {
        const params = new URLSearchParams({
            limit: "5000"
        })

        if (importId) {
            params.set("import_id", String(importId))
        }

        const res = await fetch(
            `/api/fit_timeseries/${encodeURIComponent(session_id)}?${params.toString()}`
        )

        const data = await res.json()

        const canvas =
            document.getElementById("fitChart")

        if (!canvas) {
            return
        }

        buildProfessionalChart(
            canvas,
            data.time || [],
            [
                {
                    label: "Heart Rate from FIT",
                    data: (data.pulse || []).map(toNumberOrNull),
                    borderColor: CHART_COLORS.heartRate,
                    backgroundColor: CHART_COLORS.heartRate,
                    yAxisID: "yVitals",
                    spanGaps: true
                },
                {
                    label: "SpO2",
                    data: (data.spo2 || []).map(toNumberOrNull),
                    borderColor: CHART_COLORS.spo2,
                    backgroundColor: CHART_COLORS.spo2,
                    yAxisID: "ySpo2",
                    spanGaps: true
                },
                {
                    label: "HRV RMSSD",
                    data: (data.hrv || []).map(toNumberOrNull),
                    borderColor: CHART_COLORS.hrv,
                    backgroundColor: CHART_COLORS.hrv,
                    yAxisID: "yHrv",
                    spanGaps: true
                }
            ]
        )

    } catch (err) {

        console.error("loadFitChart error", err)
    }
}

// ========================================
// FIT TABLE
// ========================================

async function loadFITTable(session_id, importId = null) {

    try {
        const params = new URLSearchParams({
            session_id,
            limit: String(FIT_CHART_TABLE_PREVIEW_LIMIT)
        })

        if (importId) {
            params.set("import_id", String(importId))
        }

        const res = await fetch(
            `/api/fit_data?${params.toString()}`
        )

        const data = await res.json()

        const tbody =
            document.querySelector("#fitDataTable tbody")

        if (!tbody) {
            return
        }

        if (!Array.isArray(data) || data.length === 0) {

            tbody.innerHTML = `
                <tr>
                    <td colspan="4">No FIT data</td>
                </tr>
            `

            return
        }

        await fitChartRenderRowsChunked(
            tbody,
            data,
            [
                row => fitChartDisplayValue(row.timestamp),
                row => fitChartDisplayValue(
                    row.heart_rate,
                    row.hr,
                    row.pulse
                ),
                row => fitChartDisplayValue(
                    row.rr_interval,
                    row.rr
                ),
                row => fitChartDisplayValue(row.hrv)
            ]
        )

    } catch (err) {

        console.error("loadFITTable error", err)
    }
}

// ========================================
// FIT UPLOAD
// ========================================

async function uploadFIT() {

    try {

        const input =
            document.getElementById("fitFile")

        if (!input || !input.files.length) {

            alert("Select FIT file")
            return
        }

        const file = input.files[0]

        const session_id =
            document.getElementById("session_id").value

        if (!session_id) {

            alert("Generate session first")
            return
        }

        const fd = new FormData()

        fd.append("file", file)
        fd.append("session_id", session_id)

        const res = await fetch("/upload_fit", {
            method: "POST",
            body: fd
        })

        const data = await res.json()
        const duplicateImport =
            res.status === 409 &&
            data &&
            data.status === "duplicate" &&
            data.import_type === "fit"

        if ((!res.ok && !duplicateImport) || (data.error && !duplicateImport)) {

            alert(data.error || "FIT upload failed")
            return
        }

        const fitStatusMessage =
            duplicateImport
                ? "FIT already imported"
                : "FIT uploaded"

        document.getElementById("fitStatus").innerHTML = `
            <div class="success-box">
                ${fitStatusMessage}<br>
                Records: ${data.records_saved || data.records || 0}
            </div>
        `

        await loadFITTable(session_id, data.import_id)
        await loadFitChart(session_id, data.import_id)

    } catch (err) {

        console.error("uploadFIT error", err)

        alert("FIT upload failed")
    }
}

// ========================================
// HELPERS
// ========================================

function getHRVColor(value) {

    if (value < 20) {
        return "red"
    }

    if (value < 40) {
        return "orange"
    }

    return "green"
}

function getColor(status) {

    if (status === "hypoxia") {
        return "red"
    }

    if (status === "stress") {
        return "orange"
    }

    return "green"
}
// ========================================
// RENDER MERGED CHART
// ========================================

function renderMergedChart(rows) {
    if (typeof Chart === "undefined") {
        console.error("Chart.js is not loaded")
        alert("Chart.js is not loaded")
        return
    }
    const canvas =
        document.getElementById("fitChart")

    if (!canvas || !rows || rows.length === 0) {
        return
    }

    const labels = rows.map(r => r.timestamp ?? r.time ?? "")

    buildProfessionalChart(
        canvas,
        labels,
        [
            {
                label: "HR from FIT",
                data: buildTimelineDataset(rows, ["hr", "heart_rate"]),
                borderColor: CHART_COLORS.heartRate,
                backgroundColor: CHART_COLORS.heartRate,
                yAxisID: "yVitals",
                spanGaps: true
            },
            {
                label: "Pulse from CSV",
                data: buildTimelineDataset(rows, ["pulse"]),
                borderColor: CHART_COLORS.pulse,
                backgroundColor: CHART_COLORS.pulse,
                yAxisID: "yVitals",
                spanGaps: true
            },
            {
                label: "SpO2 from CSV",
                data: buildTimelineDataset(
                    rows,
                    ["spo2", "SpO2", "SO2", "so2", "s02", "S02", "sp02"]
                ),
                borderColor: CHART_COLORS.spo2,
                backgroundColor: CHART_COLORS.spo2,
                yAxisID: "ySpo2",
                spanGaps: true
            },
            {
                label: "HRV RMSSD from FIT",
                data: buildTimelineDataset(rows, ["hrv"]),
                borderColor: CHART_COLORS.hrv,
                backgroundColor: CHART_COLORS.hrv,
                yAxisID: "yHrv",
                spanGaps: true
            }
        ]
    )
}
