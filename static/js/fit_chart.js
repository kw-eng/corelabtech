// static/js/fit_chart.js

let fitChart = null

// ========================================
// LOAD MAIN FIT CHART
// ========================================

async function loadFitChart(session_id) {

    try {

        const res = await fetch(
            `/api/fit_timeseries/${session_id}`
        )

        const data = await res.json()

        const canvas =
            document.getElementById("fitChart")

        if (!canvas) {
            return
        }

        const ctx = canvas.getContext("2d")

        if (fitChart) {
            fitChart.destroy()
            fitChart = null
        }

        fitChart = new Chart(ctx, {
            type: "line",

            data: {
                labels: data.time || [],

                datasets: [
                    {
                        label: "Heart Rate",
                        data: data.pulse || [],
                        borderWidth: 2
                    },
                    {
                        label: "SpO2",
                        data: data.spo2 || [],
                        borderWidth: 2
                    },
                    {
                        label: "HRV",
                        data: data.hrv || [],
                        borderWidth: 2
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

    } catch (err) {

        console.error("loadFitChart error", err)
    }
}

// ========================================
// FIT TABLE
// ========================================

async function loadFITTable(session_id) {

    try {

        const res = await fetch(
            `/api/fit_data?session_id=${session_id}`
        )

        const data = await res.json()

        const tbody =
            document.querySelector("#fitDataTable tbody")

        if (!tbody) {
            return
        }

        tbody.innerHTML = ""

        if (!Array.isArray(data) || data.length === 0) {

            tbody.innerHTML = `
                <tr>
                    <td colspan="4">No FIT data</td>
                </tr>
            `

            return
        }

        data.forEach(row => {

            tbody.innerHTML += `
                <tr>
                    <td>${row.timestamp || "-"}</td>
                    <td>${row.heart_rate || row.hr || row.pulse || "-"}</td>
                    <td>${row.rr_interval || row.rr || "-"}</td>
                    <td>${row.hrv || "-"}</td>
                </tr>
            `
        })

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

        if (!res.ok || data.error) {

            alert(data.error || "FIT upload failed")
            return
        }

        document.getElementById("fitStatus").innerHTML = `
            <div class="success-box">
                ✔ FIT uploaded<br>
                Records: ${data.records || 0}
            </div>
        `

        await loadFITTable(session_id)
        await loadFitChart(session_id)

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

    const labels =
        rows.map(r =>
            r.timestamp ??
            r.time ??
            ""
        )

    // FIT HR
    const hr =
        rows.map(r =>
            r.hr ??
            r.heart_rate ??
            r.pulse ??
            null
        )

    // CSV pulse
    const pulse =
        rows.map(r =>
            r.pulse ??
            null
        )

    // SPO2
    const spo2 =
        rows.map(r =>

            r.spo2 ??
            r.SpO2 ??
            r.SO2 ??
            r.so2 ??
            r.s02 ??
            r.S02 ??
            r.sp02 ??

            null
        )

    // HRV
    const hrv =
        rows.map(r =>
            r.hrv ??
            null
        )

    console.log("MERGED CHART DATA")
    console.log("SPO2:", spo2)

    const ctx =
        canvas.getContext("2d")

    if (fitChart) {
        fitChart.destroy()
        fitChart = null
    }

    fitChart = new Chart(ctx, {

        type: "line",

        data: {
            labels: labels,

            datasets: [

                {
                    label: "HR from FIT",
                    data: hr,
                    borderWidth: 2
                },

                {
                    label: "Pulse from CSV",
                    data: pulse,
                    borderWidth: 2
                },

                {
                    label: "SpO2 from CSV",
                    data: spo2,
                    borderWidth: 2
                },

                {
                    label: "HRV from FIT",
                    data: hrv,
                    borderWidth: 2
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
}