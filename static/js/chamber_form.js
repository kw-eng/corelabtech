// static/js/chamber_form.js

let state = {
    pre: null,
    during: null,
    post: null
}

async function parseJsonResponse(res, label) {
    const text = await res.text()

    console.log(`${label} RAW RESPONSE:`, text)

    try {
        return JSON.parse(text)
    } catch (e) {
        console.error(`${label} non-JSON response:`, text)
        return {
            status: "error",
            error: `${label} returned HTML/non-JSON`,
            raw: text
        }
    }
}

// ========================================
// INIT
// ========================================

window.onload = () => {

    loadSubjects()

    loadSessions()

    initPressurePreview()

    initOxygenPreview()

    // ========================================
    // STEP NAVIGATION
    // ========================================

    document.getElementById(
        "step_pre"
    ).onclick = () => go("pre")

    document.getElementById(
        "step_during"
    ).onclick = () => go("during")

    document.getElementById(
        "step_post"
    ).onclick = () => go("post")

    go("pre")

    updateProgress()

    // setInterval(updateRealtimeAI, 5000)
}

// ========================================
// PROGRESS
// ========================================

function updateProgress() {

    let progress = 0

    // ========================================
    // PRE
    // ========================================

    if (state.pre?.saved) {

        progress += 33

        document
            .getElementById("step_pre")
            .classList.add("done")

        document
            .getElementById("step_during")
            .classList.remove("locked")

    } else {

        document
            .getElementById("step_pre")
            .classList.remove("done")

        document
            .getElementById("step_during")
            .classList.add("locked")
    }

    // ========================================
    // DURING
    // ========================================

    if (state.during?.saved) {

        progress += 33

        document
            .getElementById("step_during")
            .classList.add("done")

        document
            .getElementById("step_post")
            .classList.remove("locked")

    } else {

        document
            .getElementById("step_during")
            .classList.remove("done")

        document
            .getElementById("step_post")
            .classList.add("locked")
    }

    // ========================================
    // POST
    // ========================================

    if (state.post?.saved) {

        progress += 34

        document
            .getElementById("step_post")
            .classList.add("done")

    } else {

        document
            .getElementById("step_post")
            .classList.remove("done")
    }

    // ========================================
    // UPDATE BAR
    // ========================================

    document.getElementById(
        "progressFill"
    ).style.width = progress + "%"

    document.getElementById(
        "progressText"
    ).innerHTML =
        "Progress: " + progress + "%"
}

// ========================================
// PREVIEW
// ========================================

function initPressurePreview() {

    const pressure =
        document.getElementById("during_pressure")

    if (!pressure) return

    pressure.addEventListener("input", () => {

        const kpa = Number(pressure.value)

        if (!kpa) {

            document.getElementById(
                "ata_preview"
            ).innerText = ""

            return
        }

        const ata = (1 + (kpa / 100)).toFixed(2)

        document.getElementById(
            "ata_preview"
        ).innerText = `ATA: ${ata}`
    })
}

function initOxygenPreview() {

    const oxygen =
        document.getElementById("during_oxygen_lpm")

    if (!oxygen) return

    oxygen.addEventListener("input", () => {

        const lpm = Number(oxygen.value)

        if (!lpm) {

            document.getElementById(
                "oxygen_preview"
            ).innerText = ""

            return
        }

        const auto =
            Math.min(96, 87 + (lpm * 1.2))

        document.getElementById(
            "oxygen_preview"
        ).innerText =
            `Auto O2: ${auto.toFixed(1)}%`

        const percent =
            document.getElementById(
                "during_oxygen_percent"
            )

        if (percent) {
            percent.value = auto.toFixed(1)
        }
    })
}

// ========================================
// NAVIGATION
// ========================================

function go(phase) {

    if (
        phase === "during" &&
        !state.pre?.saved
    ) {
        alert("Save PRE first")
        return
    }

    if (
        phase === "post" &&
        !state.during?.saved
    ) {
        alert("Save DURING first")
        return
    }

    ;["pre", "during", "post"].forEach(p => {

        document.getElementById(
            `panel_${p}`
        ).style.display = "none"

        document.getElementById(
            `step_${p}`
        ).classList.remove("active")
    })

    document.getElementById(
        `panel_${phase}`
    ).style.display = "block"

    document.getElementById(
        `step_${phase}`
    ).classList.add("active")
}

// ========================================
// SUBJECTS
// ========================================

async function createSubject() {

    const subjectId =
        document.getElementById("subject_id")
            .value
            .trim()

    if (!subjectId) {
        alert("Enter Subject ID")
        return
    }

    const payload = {

        subject_id: subjectId,

        sex:
            document.getElementById("sex").value,

        age:
            Number(
                document.getElementById("age").value
            ),

        weight:
            Number(
                document.getElementById("weight").value
            ),

        notes:
            document.getElementById("notes").value
    }

    const res = await fetch("/api/subjects", {

        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify(payload)
    })

    const data = await parseJsonResponse(res, "CREATE SUBJECT")

    if (!res.ok || data.error) {

        alert(data.error || "Create subject failed")
        return
    }

    alert("Subject created")

    await loadSubjects()
}

async function deleteSubject() {

    const subjectSelect =
        document.getElementById("user_id")

    const subjectId =
        subjectSelect.value

    const subjectLabel =
        subjectSelect.options[subjectSelect.selectedIndex]?.text || subjectId

    if (!subjectId) {
        alert("No subject selected")
        return
    }

    if (!confirm(`Are you sure you want to delete this subject and all related sessions?\n\nSubject: ${subjectLabel}\nID: ${subjectId}`)) {
        return
    }

    try {

        const res = await fetch("/api/delete_subject", {

            method: "POST",

            credentials: "same-origin",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                user_id: subjectId
            })
        })

        const text = await res.text()

        console.log("DELETE SUBJECT RAW RESPONSE:", text)

        let data = null

        try {
            data = JSON.parse(text)
        } catch (e) {
            console.error("Delete subject non-JSON response:", text)
            alert("Delete subject returned HTML. Check CSRF/auth/route.")
            return
        }

        if (!res.ok || data.error) {
            alert(data.error || "Delete subject failed")
            return
        }

        alert("Subject deleted")

        loadSubjects()

        if (typeof loadSessions === "function") {
            loadSessions()
        }

    } catch (err) {

        console.error("deleteSubject crash:", err)

        alert("Delete subject crashed - check console and Flask logs")
    }
}

async function loadSubjects() {

    const res = await fetch("/api/subjects", {
        credentials: "same-origin"
    })

    const subjects = await parseJsonResponse(res, "LOAD SUBJECTS")

    const select =
        document.getElementById("user_id")

    if (!select) {
        console.error("Select Subject element #user_id not found")
        return
    }

    select.innerHTML = ""

    if (!Array.isArray(subjects)) {
        console.error("LOAD SUBJECTS invalid response:", subjects)
        return
    }

    const onlySubjects = subjects.filter(s =>
        s &&
        s.subject_id &&
        !s.email &&
        s.role !== "admin" &&
        s.role !== "researcher"
    )

    console.log("LOAD SUBJECTS all:", subjects)
    console.log("LOAD SUBJECTS filtered:", onlySubjects)

    onlySubjects.forEach(subject => {

        const value =
            subject.user_id || subject.subject_id

        const label =
            subject.subject_id || subject.user_id

        if (!value || !label) return

        select.innerHTML += `
            <option value="${value}">
                ${label}
            </option>
        `
    })

    if (select.options.length > 0) {
        generateSession()
    } else {
        document.getElementById("session_id").value = ""
    }
}

// ========================================
// SESSION
// ========================================

function generateSession() {

    const subject =
        document.getElementById("user_id")?.value

    if (!subject) return

    document.getElementById(
        "session_id"
    ).value =
        `${subject}_${Date.now()}`

    state = {
        pre: null,
        during: null,
        post: null
    }

    document.getElementById(
        "preview_pre"
    ).innerHTML = ""

    document.getElementById(
        "preview_during"
    ).innerHTML = ""

    document.getElementById(
        "preview_post"
    ).innerHTML = ""

    document.getElementById(
        "preview_full"
    ).innerHTML = ""

    updateProgress()

    go("pre")
}

// ========================================
// PRE
// ========================================

async function savePRE() {

    const spo2 =
        Number(
            document.getElementById(
                "pre_spo2"
            ).value
        )

    const pulse =
        Number(
            document.getElementById(
                "pre_pulse"
            ).value
        )

    if (!spo2 || !pulse) {

        alert("Fill PRE data")
        return
    }

    try {

        state.pre = {

            saved: true,

            phase: "pre",

            spo2: spo2,

            pulse: pulse
        }

    const res = await fetch(
    "/api/save_phase",
    {

        method: "POST",

        credentials: "same-origin",

        headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({

                    session_id:
                        document.getElementById(
                            "session_id"
                        ).value,

                    user_id:
                        document.getElementById(
                            "user_id"
                        ).value,

                    phase: "pre",

                    spo2: spo2,

                    pulse: pulse
                })
            }
        )

    const data = await parseJsonResponse(res, "SAVE PRE")

        if (!res.ok || data.error) {

            state.pre = null

            alert(
                data.error ||
                "PRE save failed"
            )

            return
        }

        document
            .getElementById("step_pre")
            .classList.add("done")

        updateProgress()

        document.getElementById(
            "preview_pre"
        ).innerHTML = `

            <div class="success-box">

                <b>✔ PRE SAVED</b>

                <br><br>

                Session:
                ${document.getElementById("session_id").value}

                <br>

                SpO2:
                ${spo2}%

                <br>

                Pulse:
                ${pulse} bpm

            </div>
        `

        requestAnimationFrame(() => {

            requestAnimationFrame(() => {

                go("during")

            })

        })

        alert("PRE saved successfully")

    } catch (err) {

        console.error(err)

        state.pre = null

        alert("Server error during PRE save")
    }
}

// ========================================
// FIT
// ========================================

async function uploadFIT() {

    let input =
        document.getElementById("fitFile")

    if (!input.files.length) {

        alert("Select FIT file")
        return
    }

    let file = input.files[0]

    let fd = new FormData()

    fd.append("file", file)

    fd.append(
        "session_id",
        document.getElementById(
            "session_id"
        ).value
    )

    try {

let res = await fetch(
    "/upload_fit",
    {
        method: "POST",
        credentials: "same-origin",
        body: fd
    }
)

let data = await parseJsonResponse(res, "UPLOAD FIT")

        if (!res.ok || data.error) {

            console.error(data)

            alert(
                data.error ||
                "FIT upload failed"
            )

            return
        }

        document.getElementById(
            "fitStatus"
        ).innerHTML = `

            <div class="success-box">

                ✔ FIT uploaded

                <br>

                Records:
                ${data.records || 0}

            </div>
        `

        await loadFITTable(
            document.getElementById(
                "session_id"
            ).value
        )

        if (typeof loadFitChart === "function") {

            loadFitChart(
                document.getElementById(
                    "session_id"
                ).value
            )
        }

    } catch (err) {

        console.error(err)

        alert("FIT upload server error")
    }
}

async function loadFITTable(session) {

let res = await fetch(
    "/api/fit_data?session_id=" + session,
    {
        credentials: "same-origin"
    }
)

let data = await parseJsonResponse(res, "LOAD FIT DATA")

    let tbody =
        document.querySelector(
            "#fitDataTable tbody"
        )

    tbody.innerHTML = ""

    if (!Array.isArray(data)) {

        console.error(data)

        tbody.innerHTML = `
            <tr>
                <td colspan="4">
                    Invalid FIT data
                </td>
            </tr>
        `

        return
    }

    if (data.length === 0) {

        tbody.innerHTML = `
            <tr>
                <td colspan="4">
                    No FIT records
                </td>
            </tr>
        `

        return
    }

    data.forEach(r => {

        const time =
            r.timestamp ||
            r.time ||
            "-"

        const hr =
            r.heart_rate ||
            r.hr ||
            r.pulse ||
            "-"

        const rr =
            r.rr ||
            r.rr_interval ||
            r.rr_intervals ||
            "-"

        const hrv =
            r.hrv ||
            r.rmssd ||
            "-"

        tbody.innerHTML += `

            <tr>

                <td>${time}</td>

                <td>${hr}</td>

                <td>${rr}</td>

                <td>${hrv}</td>

            </tr>
        `
    })
}

// ========================================
// CSV
// ========================================

async function uploadCSV() {

    let input =
        document.getElementById("csvFile")

    if (!input.files.length) {

        alert("Select CSV file")
        return
    }

    let file = input.files[0]

    let fd = new FormData()

    fd.append("file", file)

    fd.append(
        "session_id",
        document.getElementById(
            "session_id"
        ).value
    )

    try {

let res = await fetch(
    "/upload_csv",
    {
        method: "POST",
        credentials: "same-origin",
        body: fd
    }
)

let data = await parseJsonResponse(res, "UPLOAD CSV")

        if (!res.ok || data.error) {

            alert(
                data.error ||
                "CSV upload failed"
            )

            return
        }

        document.getElementById(
            "csvStatus"
        ).innerHTML = `

            <div class="success-box">

                ✔ CSV uploaded

                <br>

                Records:
                ${data.records || 0}

            </div>
        `

        await loadCSVTable(
            document.getElementById(
                "session_id"
            ).value
        )

    } catch (err) {

        console.error(err)

        alert("CSV upload server error")
    }
}

async function loadCSVTable(session) {

let res = await fetch(
    "/api/csv_data?session_id=" + session,
    {
        credentials: "same-origin"
    }
)

let data = await parseJsonResponse(res, "LOAD CSV DATA")

    let tbody =
        document.querySelector(
            "#csvDataTable tbody"
        )

    tbody.innerHTML = ""

    if (!Array.isArray(data)) {

        tbody.innerHTML = `
            <tr>
                <td colspan="3">
                    Invalid CSV data
                </td>
            </tr>
        `

        return
    }

    if (data.length === 0) {

        tbody.innerHTML = `
            <tr>
                <td colspan="3">
                    No CSV records
                </td>
            </tr>
        `

        return
    }

    data.forEach(r => {

        const time =
            r.timestamp ||
            r.time ||
            "-"

        const pulse =
            r.pulse ||
            r.hr ||
            r.heart_rate ||
            "-"

        const spo2 =
            r.spo2 ||
            r.oxygen ||
            r.saturation ||
            "-"

        tbody.innerHTML += `

            <tr>

                <td>${time}</td>

                <td>${pulse}</td>

                <td>${spo2}</td>

            </tr>
        `
    })
}

// ========================================
// MERGE DURING
// ========================================
async function mergeDuring() {

    console.log("MERGE CLICKED")

    const sessionId =
        document.getElementById("session_id").value

    console.log("MERGE SESSION ID:", sessionId)

    if (!sessionId) {
        alert("No session_id")
        return []
    }

    try {

        const res = await fetch("/api/during_merge", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        })


        const data = await parseJsonResponse(res, "MERGE DURING")

        if (data.error && data.raw) {
            alert("Backend returned HTML/non-JSON response")
            return []
}

        if (!res.ok || data.error) {
            console.error("Merge backend error:", data)
            alert(data.error || "Merge failed")
            return []
        }

        const merged =
            data.merged ||
            data.timeline ||
            data.data ||
            []

        renderMergedTable(merged)

        if (typeof renderMergedChart === "function") {
            renderMergedChart(merged)
        }

        const status =
            document.getElementById("mergeStatus")

        if (status) {
            status.innerHTML = `
                <div class="success-box">
                    ✔ Merge completed<br>
                    Mode: ${data.mode || "-"}<br>
                    FIT samples: ${data.fit_samples ?? "-"}<br>
                    CSV samples: ${data.csv_samples ?? "-"}<br>
                    Merged samples: ${merged.length}
                </div>
            `
        }

        console.log("MERGED:", merged)

        return merged

    } catch (err) {

        console.error("mergeDuring crash:", err)
        alert("Merge crashed - check Flask terminal and browser console")
        return []
    }
}

// ========================================
// RENDER MERGED TABLE
// ========================================
function renderMergedTable(rows) {

    const tbody =
        document.querySelector("#mergedDataTable tbody")

    if (!tbody) {
        return
    }

    tbody.innerHTML = ""

    if (!rows || rows.length === 0) {

        tbody.innerHTML = `
            <tr>
                <td colspan="7">No merged data</td>
            </tr>
        `

        return
    }

    rows.forEach(r => {

        const spo2 =
            r.spo2 ??
            r.SpO2 ??
            r.SO2 ??
            r.so2 ??
            r.s02 ??
            r.S02 ??
            r.sp02 ??
            "-"

        tbody.innerHTML += `
            <tr>
                <td>${r.timestamp || r.time || "-"}</td>
                <td>${r.hr || r.heart_rate || "-"}</td>
                <td>${r.pulse || "-"}</td>
                <td>${r.rr_interval || r.rr || "-"}</td>
                <td>${r.hrv || "-"}</td>
                <td>${spo2}</td>
                <td>${r.source || "merged"}</td>
            </tr>
        `
    })
}


// ========================================
// DURING
// ========================================

async function saveDURING() {

    const sessionId =
        document.getElementById("session_id").value

    const subjectId =
        document.getElementById("user_id").value

    const pressure =
        Number(document.getElementById("during_pressure").value)

    const temp =
        Number(document.getElementById("during_temp").value)

    const bodyTemp =
        Number(document.getElementById("during_body_temp").value)

    const humidity =
        Number(document.getElementById("during_humidity").value)

    const oxygenLpm =
        Number(document.getElementById("during_oxygen_lpm").value)

    const oxygenPercent =
        Number(document.getElementById("during_oxygen_percent").value)

    if (!pressure || !temp) {
        alert("Fill chamber data")
        return
    }

    const ata =
        1 + (pressure / 100)

    const fitRes =
    await fetch("/api/fit_data?session_id=" + sessionId, {
        credentials: "same-origin"
    })

    const fit =
    await parseJsonResponse(fitRes, "DURING LOAD FIT")

    const csvRes =
    await fetch("/api/csv_data?session_id=" + sessionId, {
        credentials: "same-origin"
    })

    const csv =
    await parseJsonResponse(csvRes, "DURING LOAD CSV")

    const hasFIT =
        fit && fit.length > 0

    const hasCSV =
        csv && csv.length > 0

    if (!hasFIT && !hasCSV) {
        alert("Upload FIT or CSV first")
        return
    }

    const merged =
        await mergeDuring()

    if (!merged || merged.length === 0) {
        alert("Merge failed or no merged data")
        return
    }

    const latestMerged =
        merged[merged.length - 1] || {}

    state.during = {
        saved: true,
        phase: "during",
        pressure_kpa: pressure,
        pressure_ata: ata,
        chamber_temperature: temp,
        body_temperature: bodyTemp,
        humidity: humidity,
        oxygen_flow_lpm: oxygenLpm,
        oxygen_mask_percent: oxygenPercent,
        fit: fit,
        csv: csv,
        merged: merged
    }

    const saveRes = await fetch("/api/save_phase", {
    method: "POST",
    credentials: "same-origin",
    headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            session_id: sessionId,
            user_id: subjectId,
            phase: "during",
            pressure_kpa: pressure,
            pressure_ata: ata,
            chamber_temperature: temp,
            body_temperature: bodyTemp,
            humidity: humidity,
            oxygen_flow_lpm: oxygenLpm,
            oxygen_mask_percent: oxygenPercent,
            spo2: latestMerged.spo2,
            pulse:
                latestMerged.pulse ||
                latestMerged.heart_rate ||
                latestMerged.hr,
            hrv: latestMerged.hrv,
            rr_interval:
                latestMerged.rr_interval ||
                latestMerged.rr
        })
    })
    const saveData =
    await parseJsonResponse(saveRes, "SAVE DURING")

    if (!saveRes.ok || saveData.error) {
        alert(saveData.error || "DURING save failed")
        return
    }

    document.getElementById("preview_during").innerHTML = `
        <div class="warning-box">
            <b>✔ DURING SAVED</b><br><br>

            ATA: ${ata.toFixed(2)}<br>
            Temp: ${temp}°C<br>
            O2: ${oxygenPercent || "-"}%<br><br>

            FIT Samples: ${hasFIT ? fit.length : 0}<br>
            CSV Samples: ${hasCSV ? csv.length : 0}<br>
            Merged Samples: ${merged.length}
        </div>
    `

    await fetch("/api/push_telemetry", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            spo2: latestMerged.spo2,
            pulse:
                latestMerged.pulse ||
                latestMerged.heart_rate ||
                latestMerged.hr,
            hrv: latestMerged.hrv,
            rr_interval:
                latestMerged.rr_interval ||
                latestMerged.rr,
            pressure_ata: ata
        })
    })

    document
        .getElementById("step_during")
        .classList.add("done")

    updateProgress()

    requestAnimationFrame(() => {
        go("post")
    })

    alert("DURING saved")
}

// ========================================
// POST
// ========================================

async function savePOST() {

    const spo2 =
        Number(
            document.getElementById(
                "post_spo2"
            ).value
        )

    const pulse =
        Number(
            document.getElementById(
                "post_pulse"
            ).value
        )

    if (!spo2 || !pulse) {

        alert("Fill POST data")
        return
    }

    state.post = {

        saved: true,

        phase: "post",

        spo2: spo2,

        pulse: pulse
    }

    const res = await fetch(
        "/api/save_phase",
        {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({

                session_id:
                    document.getElementById(
                        "session_id"
                    ).value,

                user_id:
                    document.getElementById(
                        "user_id"
                    ).value,

                phase: "post",

                spo2: spo2,

                pulse: pulse
            })
        }
    )

    const data = await parseJsonResponse(res, "SAVE POST")

    if (!res.ok || data.error) {
        console.error("POST save error:", data)
        alert(data.error || "POST save failed")
        return []
    }


    document.getElementById(
        "preview_post"
    ).innerHTML = `

        <div class="success-box">

            ✔ POST SAVED

            <br><br>

            SpO2:
            ${spo2}%

            <br>

            Pulse:
            ${pulse} bpm

        </div>
    `

    document
        .getElementById("step_post")
        .classList.add("done")

    updateProgress()

    // await saveFullSession()

    alert("POST saved")
}

// ========================================
// SAVE FULL SESSION
// ========================================

async function saveFullSession() {

    if (
        !state.pre ||
        !state.during ||
        !state.post
    ) {
        alert("Complete all phases")
        return
    }

    const subjectSelect =
        document.getElementById("user_id")

    const selectedSubjectLabel =
        subjectSelect.options[subjectSelect.selectedIndex]?.text ||
        subjectSelect.value

    const payload = {
        session_id: document.getElementById("session_id").value,
        user_id: document.getElementById("user_id").value,
        pre: state.pre,
        during: state.during,
        post: state.post
    }

    try {

        const res = await fetch("/api/save_full_session", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        })

        const text = await res.text()

        console.log("SAVE FULL RAW RESPONSE:", text)

        let data = null

        try {
            data = JSON.parse(text)
        } catch (e) {
            console.error("Save full session non-JSON:", text)
            alert("Save full session returned HTML. Check Flask logs.")
            return
        }

        // alert(JSON.stringify(data))

        console.log("SAVE FULL RESPONSE:", data)

        if (!res.ok || data.error) {
            alert(data.error || "Save failed")
            return
        }

        if (data.saved_count !== 1) {
            alert("Backend did not confirm save. saved_count=" + data.saved_count)
            return
        }

        document.getElementById("preview_full").innerHTML = `
            <div class="success-box">
                <b>✔ FULL SESSION SAVED</b><br><br>
                Session: ${payload.session_id}<br>
                Subject: ${selectedSubjectLabel}<br>
                DB saved_count: ${data.saved_count}
            </div>
        `

        await loadSessions()

        try {
            await runAnalysis(payload.session_id)
        } catch (aiErr) {
            console.error("AI after save failed:", aiErr)
        }

        alert("Full session saved")

    } catch (err) {

        console.error("saveFullSession error:", err)

        alert("Network/server error")
    }
}

// ========================================
// SESSIONS
// ========================================

async function loadSessions() {

    const res =
        await fetch("/api/sessions", {
            credentials: "same-origin"
        })

    const data =
        await parseJsonResponse(res, "LOAD SESSIONS")

    const sessions =
        Array.isArray(data)
            ? data
            : Array.isArray(data.sessions)
                ? data.sessions
                : []

    const tbody =
        document.querySelector("#sessionsTable tbody")

    if (!tbody) {
        return
    }

    tbody.innerHTML = ""

    if (!sessions || sessions.length === 0) {

        tbody.innerHTML = `
            <tr>
                <td colspan="4">No saved sessions</td>
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
                        class="session_cb"
                        value="${s.session_id}"
                    >
                </td>

                <td>${s.session_id}</td>
                <td>${s.subject_id || "-"}</td>

                <td>
                    <button onclick="runAnalysis('${s.session_id}')">
                        AI
                    </button>
                </td>
            </tr>
        `
    })
}

function toggleAll(master) {

    document
        .querySelectorAll(".session_cb")
        .forEach(
            cb => cb.checked = master.checked
        )
}

async function deleteSessions() {

    const sessions = []

    document
        .querySelectorAll(".session_cb:checked")
        .forEach(
            cb => sessions.push(cb.value)
        )

    if (sessions.length === 0) {

        alert("No sessions selected")
        return
    }

const res = await fetch("/api/delete_sessions", {

    method: "POST",
    credentials: "same-origin",
    headers: {
        "Content-Type": "application/json"
    },

    body: JSON.stringify({
        sessions: sessions
    })
})

const data = await parseJsonResponse(res, "DELETE SESSIONS")

if (!res.ok || data.error) {
    alert(data.error || "Delete sessions failed")
    return
}

loadSessions()

}

// ========================================
// AI
// ========================================

async function runAnalysis(sessionId) {

    try {

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

        const data = await parseJsonResponse(res, "RUN ANALYSIS")

        if (data.error && data.raw) {
        alert("AI analysis returned HTML/non-JSON response")
        return
}

        console.log("AI RESPONSE:", data)

        if (!res.ok || data.error) {
            alert(data.error || "AI analysis failed")
            return
        }

        const anomalyText =
            data.anomaly
                ? "YES - abnormal response detected"
                : "NO critical anomaly detected"

        document.getElementById("ai-summary").innerHTML =
            "<b>Summary:</b> " + (data.summary || "-")

        document.getElementById("ai-score").innerHTML =
            "<b>Score:</b> " + (data.score ?? "-") + " / 100"

        document.getElementById("ai-anomaly").innerHTML =
            "<b>Anomaly:</b> " + anomalyText

        renderAIVisualization(data)

    } catch (err) {

        console.error("runAnalysis crash:", err)
        alert("AI analysis crashed")
    }
}

// ========================================
// render AI Visualization
// ========================================

function renderAIVisualization(data) {

    const container =
        document.getElementById("chartsContainer")

    if (!container) {
        console.error("chartsContainer not found")
        return
    }

    const features =
        data.features || {}

    const timeline =
        Array.isArray(data.timeline)
            ? data.timeline
            : Array.isArray(data.merged)
                ? data.merged
                : []

    const riskLabel =
        data.risk_level ||
        (
            data.score >= 90
                ? "Low"
                : data.score >= 70
                    ? "Moderate"
                    : "High"
        )

    const anomalyLabel =
        data.anomaly
            ? "YES - abnormal response detected"
            : "NO critical anomaly detected"

    const warnings =
        data.reasons && data.reasons.length
            ? data.reasons.join("<br>")
            : "No rule-based warning detected"

    const positiveFindings =
        data.positive_findings && data.positive_findings.length
            ? data.positive_findings.join("<br>")
            : "No additional positive findings"

    const disclaimer =
        data.medical_disclaimer ||
        "Research-only score. Not a medical diagnosis."

    const scoreReference = `
        90-100 = Low risk / stable session<br>
        70-89 = Moderate warning / observe session<br>
        below 70 = High risk / review required
    `

    const scoreMeaning = `
        The score starts at 100 and is reduced when rule-based warnings are detected:
        low SpO2, large PRE to POST SpO2 drop, elevated HR/pulse, or low HRV.
    `

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
                        <td><b>Score meaning</b></td>
                        <td>${scoreMeaning}</td>
                    </tr>

                    <tr>
                        <td><b>Score reference</b></td>
                        <td>${scoreReference}</td>
                    </tr>

                    <tr>
                        <td><b>Risk level</b></td>
                        <td>${riskLabel}</td>
                    </tr>

                    <tr>
                        <td><b>Anomaly</b></td>
                        <td>${anomalyLabel}</td>
                    </tr>

                    <tr>
                        <td><b>AI warnings</b></td>
                        <td>${warnings}</td>
                    </tr>

                    <tr>
                        <td><b>Positive findings</b></td>
                        <td>${positiveFindings}</td>
                    </tr>

                    <tr>
                        <td><b>Summary</b></td>
                        <td>${data.summary || "-"}</td>
                    </tr>

                    <tr>
                        <td><b>Disclaimer</b></td>
                        <td>${disclaimer}</td>
                    </tr>

                </tbody>
            </table>

        </div>

        <div class="panel">

            <h3>Signal Quality</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr>
                        <td>FIT samples</td>
                        <td>${features.fit_samples ?? "-"}</td>
                    </tr>
                    <tr>
                        <td>CSV samples</td>
                        <td>${features.csv_samples ?? "-"}</td>
                    </tr>
                    <tr>
                        <td>CSV pulse artifacts ignored</td>
                        <td>${features.csv_pulse_artifacts ?? 0}</td>
                    </tr>
                    <tr>
                        <td>Timeline samples for chart</td>
                        <td>${timeline.length}</td>
                    </tr>
                </tbody>
            </table>

        </div>

        <div class="panel">

            <h3>Physiology Metrics</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr>
                        <td>Avg SpO2 from CSV</td>
                        <td>${features.avg_csv_spo2 ?? "-"} %</td>
                    </tr>
                    <tr>
                        <td>Min SpO2 from CSV</td>
                        <td>${features.min_spo2 ?? "-"} %</td>
                    </tr>
                    <tr>
                        <td>Max SpO2 from CSV</td>
                        <td>${features.max_spo2 ?? "-"} %</td>
                    </tr>
                    <tr>
                        <td>Avg Pulse from CSV</td>
                        <td>${features.avg_csv_pulse ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Min Pulse from CSV</td>
                        <td>${features.min_csv_pulse ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Max Pulse from CSV</td>
                        <td>${features.max_csv_pulse ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Avg HR from FIT</td>
                        <td>${features.avg_fit_hr ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Min HR from FIT</td>
                        <td>${features.min_fit_hr ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Max HR from FIT</td>
                        <td>${features.max_fit_hr ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Avg HRV from FIT</td>
                        <td>${features.avg_hrv ?? "-"} ms</td>
                    </tr>
                </tbody>
            </table>

        </div>

        <div class="panel">

            <h3>AI Rules</h3>

            <table border="1" style="width:100%;">
                <tbody>
                    <tr>
                        <td>SpO2 high warning</td>
                        <td>&lt; 90%</td>
                    </tr>
                    <tr>
                        <td>SpO2 warning</td>
                        <td>90-91%</td>
                    </tr>
                    <tr>
                        <td>SpO2 borderline</td>
                        <td>92-93%</td>
                    </tr>
                    <tr>
                        <td>PRE → POST SpO2 drop</td>
                        <td>≥ 3% warning, ≥ 5% stronger warning</td>
                    </tr>
                    <tr>
                        <td>Pulse / HR anomaly threshold</td>
                        <td>&gt; 160 bpm</td>
                    </tr>
                    <tr>
                        <td>HRV anomaly threshold</td>
                        <td>&lt; 30 ms</td>
                    </tr>
                </tbody>
            </table>

        </div>

        <div class="panel chart-box" style="height:380px; min-height:380px; position:relative;">

            <h3>AI Timeline</h3>

            <canvas
                id="aiTimelineChart"
                style="width:100%; height:320px;"
            ></canvas>

            <div id="aiTimelineStatus"></div>

        </div>
    `

    const status =
        document.getElementById("aiTimelineStatus")

    if (!timeline.length) {

        if (status) {
            status.innerHTML = `
                <div class="warning-box">
                    No timeline data available for chart.
                </div>
            `
        }

        console.warn("AI timeline empty:", data)
        return
    }

    if (typeof Chart === "undefined") {

        if (status) {
            status.innerHTML = `
                <div class="warning-box">
                    Chart.js is not loaded.
                </div>
            `
        }

        console.error("Chart.js is not loaded")
        return
    }

    const labels =
        timeline.map(r => r.timestamp || r.time || "")

    const spo2 =
        timeline.map(r =>
            r.spo2 ??
            r.SpO2 ??
            r.SO2 ??
            null
        )

    const pulse =
        timeline.map(r => {

            const value =
                r.pulse ??
                r.csv_pulse ??
                null

            if (value !== null && Number(value) < 30) {
                return null
            }

            return value !== null ? Number(value) : null
        })

    const heartRate =
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
                r.hrv ??
                null

            return value !== null ? Number(value) : null
        })

    const hasAnyData =
        spo2.some(v => v !== null) ||
        pulse.some(v => v !== null) ||
        heartRate.some(v => v !== null) ||
        hrv.some(v => v !== null)

    if (!hasAnyData) {

        if (status) {
            status.innerHTML = `
                <div class="warning-box">
                    Timeline exists, but no numeric values were found for chart.
                </div>
            `
        }

        console.warn("Timeline without numeric chart values:", timeline)
        return
    }

    const canvas =
        document.getElementById("aiTimelineChart")

    if (!canvas) {

        console.error("aiTimelineChart canvas not found")
        return
    }

    if (
        window.aiTimelineChart &&
        typeof window.aiTimelineChart.destroy === "function"
    ) {
        window.aiTimelineChart.destroy()
    }

    window.aiTimelineChart = null

    try {

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
                        data: heartRate,
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

        if (status) {
            status.innerHTML = `
                <div class="success-box">
                    Timeline chart rendered. Samples: ${timeline.length}
                </div>
            `
        }

    } catch (err) {

        console.error("AI timeline chart render error:", err)

        if (status) {
            status.innerHTML = `
                <div class="warning-box">
                    Chart render error. Check browser console.
                </div>
            `
        }
    }
}

// ========================================
// REALTIME AI
// ========================================

async function updateRealtimeAI() {

    try {

    const res =
    await fetch("/api/ai_latest", {
        credentials: "same-origin"
    })

    const data =
    await parseJsonResponse(res, "REALTIME AI")

        if (data.error) {
            return
        }

        document.getElementById(
            "liveScore"
        ).innerHTML = `

            <div class="info-box">

                <h2>
                    AI Score:
                    ${data.score}
                </h2>

                <div>
                    Anomaly:
                    ${data.anomaly}
                </div>

                <div>
                    ${data.summary || ""}
                </div>

            </div>
        `

    } catch (e) {

        console.error(e)
    }
}
window.createSubject = createSubject
window.deleteSubject = deleteSubject
window.loadSubjects = loadSubjects
window.generateSession = generateSession

window.savePRE = savePRE
window.uploadFIT = uploadFIT
window.uploadCSV = uploadCSV
window.loadFITTable = loadFITTable
window.loadCSVTable = loadCSVTable

window.mergeDuring = mergeDuring
window.renderMergedTable = renderMergedTable

window.saveDURING = saveDURING
window.savePOST = savePOST
window.saveFullSession = saveFullSession

window.loadSessions = loadSessions
window.deleteSessions = deleteSessions
window.toggleAll = toggleAll

window.runAnalysis = runAnalysis
window.renderAIVisualization = renderAIVisualization
window.updateRealtimeAI = updateRealtimeAI