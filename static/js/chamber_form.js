// static/js/chamber_form.js

let state = {
    pre: null,
    during: null,
    post: null,
    chambers: [],
    protocols: [],
    programs: [],
    enrollments: []
}

const STANDARD_ATMOSPHERE_KPA = 101.325
const DEFAULT_PRESSURE_INPUT_UNIT = "kpa_gauge"
const PRESSURE_OPERATIONAL_TOLERANCE_ATA = 0.05
const CONCENTRATOR_MIN_FLOW_LPM = 2
const CONCENTRATOR_MAX_FLOW_LPM = 10
const CONCENTRATOR_MIN_OXYGEN_PERCENT = 87
const CONCENTRATOR_MAX_OXYGEN_PERCENT = 96
const TABLE_PREVIEW_LIMIT = 5000
const TABLE_RENDER_CHUNK_SIZE = 100
const FIT_UPLOAD_TIMEOUT_MS = 120000
const GENERATED_SESSION_SUFFIX_PATTERN = /_\d{10,}$/
let compatibilityDevices = []

function i18n(key, params = null) {
    if (typeof window !== "undefined" && typeof window.t === "function") {
        return window.t(key, params)
    }

    return key
}

async function parseJsonResponse(res, label) {
    const text = await res.text()

    console.log(
        `${label} response:`,
        {
            ok: res.ok,
            status: res.status,
            bytes: text.length,
            preview: text.slice(0, 300)
        }
    )

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

function waitForNextFrame() {
    return new Promise(resolve => {
        if (typeof requestAnimationFrame === "function") {
            requestAnimationFrame(resolve)
            return
        }

        setTimeout(resolve, 0)
    })
}

async function renderTableRowsChunked(tbody, rows, columns) {
    tbody.replaceChildren()

    for (
        let start = 0;
        start < rows.length;
        start += TABLE_RENDER_CHUNK_SIZE
    ) {
        const fragment =
            document.createDocumentFragment()

        rows
            .slice(start, start + TABLE_RENDER_CHUNK_SIZE)
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

        if (start + TABLE_RENDER_CHUNK_SIZE < rows.length) {
            await waitForNextFrame()
        }
    }
}

function displayValue(...values) {
    const value = values.find(item => (
        item !== undefined &&
        item !== null &&
        item !== ""
    ))

    return value === undefined ? "-" : value
}

function setText(id, text) {
    const element =
        document.getElementById(id)

    if (element) {
        element.textContent = text
    }
}

function normalizeSubjectId(value) {
    let subjectId = String(value || "").trim()

    while (GENERATED_SESSION_SUFFIX_PATTERN.test(subjectId)) {
        subjectId = subjectId.replace(GENERATED_SESSION_SUFFIX_PATTERN, "")
    }

    return subjectId
}

function looksLikeGeneratedSessionId(value) {
    return GENERATED_SESSION_SUFFIX_PATTERN.test(String(value || "").trim())
}

function getSelectedSubjectId() {
    return normalizeSubjectId(
        document.getElementById("user_id")?.value
    )
}

function inputValue(id) {
    const element = document.getElementById(id)

    return element ? element.value.trim() : ""
}

function parseLocalizedNumber(value) {
    if (value === null || value === undefined || value === "") {
        return null
    }

    const normalized = String(value).trim().replace(",", ".")
    const number = Number(normalized)

    return Number.isFinite(number) ? number : null
}

function numericInputValue(id) {
    return parseLocalizedNumber(inputValue(id))
}

function optionalNumberInput(id) {
    return numericInputValue(id)
}

function collectPreCheckIn() {
    return {
        sleep_hours: numericInputValue("pre_sleep_hours"),
        sleep_quality: inputValue("pre_sleep_quality") || null,
        stress_level: inputValue("pre_stress_level") || null,
        training_load_24h: inputValue("pre_training_load") || null,
        fatigue_level: inputValue("pre_fatigue_level") || null,
        session_goal: inputValue("pre_session_goal") || null,
        notes: inputValue("pre_context_notes") || null
    }
}

function collectPostCheckOut() {
    return {
        energy_level: inputValue("post_energy_level") || null,
        relaxation_level: inputValue("post_relaxation_level") || null,
        fatigue_level: inputValue("post_fatigue_level") || null,
        discomfort: inputValue("post_discomfort") || null,
        notes: inputValue("post_context_notes") || null
    }
}

function hasContextValues(context) {
    return Object.values(context || {}).some(
        value => value !== null && value !== ""
    )
}

function contextPreview(context) {
    if (!hasContextValues(context)) {
        return i18n("chamber.no_checkin_context")
    }

    return Object.entries(context)
        .filter(([, value]) => value !== null && value !== "")
        .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`)
        .join("<br>")
}

function clearMergedPreview() {
    const tbody =
        document.querySelector("#mergedDataTable tbody")

    if (tbody) {
        tbody.replaceChildren()
    }

    const status =
        document.getElementById("mergeStatus")

    if (status) {
        status.innerHTML = ""
    }

    if (typeof fitChart !== "undefined" && fitChart) {
        fitChart.destroy()
        fitChart = null
    }
}

// ========================================
// INIT
// ========================================

window.onload = () => {

    loadSubjects()

    loadDeviceCompatibility()

    loadSessions()

    loadSessionConfiguration()

    loadCommercialContext()

    document.getElementById("use_detailed_timeline")?.addEventListener(
        "change",
        toggleDetailedTimeline
    )

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
        i18n("chamber.progress", {progress})
}

// ========================================
// PREVIEW
// ========================================

function initPressurePreview() {

    const pressure =
        document.getElementById("during_pressure")
    const pressureUnit =
        document.getElementById("during_pressure_unit")
    const protocol =
        document.getElementById("protocol_id")

    if (!pressure) return

    pressure.addEventListener("input", updatePressurePreview)
    pressureUnit?.addEventListener("change", updatePressurePreview)
    protocol?.addEventListener("change", updatePressurePreview)
}

function pressureToAta(value, unit) {
    const numericValue = parseLocalizedNumber(value)

    if (!Number.isFinite(numericValue) || numericValue <= 0) {
        return null
    }

    if (unit === "ata") {
        return numericValue
    }

    if (unit === "kpa_absolute") {
        return numericValue / STANDARD_ATMOSPHERE_KPA
    }

    if (unit === "kpa_gauge") {
        return 1 + (numericValue / STANDARD_ATMOSPHERE_KPA)
    }

    return null
}

function getSelectedProtocol() {
    const protocolId =
        Number(document.getElementById("protocol_id")?.value)

    return state.protocols.find(
        protocol => Number(protocol.protocol_id) === protocolId
    ) || null
}

function protocolPhaseValue(protocol, field, fallback = 0) {
    const value = Number(protocol?.[field])
    return Number.isFinite(value) ? value : fallback
}

function updateDurationPreview() {
    const compression = Number(
        document.getElementById("during_compression_min")?.value
    )
    const exposure = Number(
        document.getElementById("during_exposure_min")?.value
    )
    const decompression = Number(
        document.getElementById("during_decompression_min")?.value
    )
    const values = [compression, exposure, decompression]

    if (values.some(value => !Number.isFinite(value) || value < 0)) {
        setText("duration_preview", i18n("chamber.enter_valid_durations"))
        return
    }

    const total = compression + exposure + decompression
    setText(
        "duration_preview",
        i18n("chamber.duration_preview", {
            compression,
            exposure,
            decompression,
            total
        })
    )

    const protocol = getSelectedProtocol()
    if (protocol) {
        const differs =
            compression !== Number(protocol.compression_time_min) ||
            exposure !== Number(protocol.exposure_time_min) ||
            decompression !== Number(protocol.decompression_time_min)
        if (differs) {
            document.getElementById("during_execution_status").value =
                "modified"
        }
    }
}

async function loadCommercialContext() {
    try {
        const [contextResponse, programsResponse] = await Promise.all([
            fetch("/api/organization/context", {credentials: "same-origin"}),
            fetch("/api/programs", {credentials: "same-origin"})
        ])
        const context = await parseJsonResponse(
            contextResponse,
            "LOAD ORGANIZATION"
        )
        const programs = await parseJsonResponse(
            programsResponse,
            "LOAD PROGRAMS"
        )
        if (contextResponse.ok) {
            setText(
                "organization_context",
                `${context.organization_name} | ${context.location_name}`
            )
        }
        if (programsResponse.ok && Array.isArray(programs)) {
            state.programs = sortProgramsBySize(programs)
            const select = document.getElementById("program_catalog")
            select.replaceChildren()
            state.programs.forEach(program => {
                const option = document.createElement("option")
                option.value = program.program_id
                option.textContent =
                    i18n("chamber.program_sessions", {
                        name: program.name,
                        total: program.total_sessions
                    })
                select.appendChild(option)
            })
        }
    } catch (error) {
        console.error("Commercial context load failed:", error)
    }
}

function sortProgramsBySize(programs) {
    return programs.slice().sort((a, b) => {
        const aSessions = Number(a.total_sessions) || 0
        const bSessions = Number(b.total_sessions) || 0

        if (aSessions !== bSessions) {
            return aSessions - bSessions
        }

        const aName = String(a.name || a.program_name || "")
        const bName = String(b.name || b.program_name || "")

        return aName.localeCompare(bName)
    })
}

async function loadClientPrograms(preferredEnrollmentId = null) {
    const clientId = getSelectedSubjectId()
    const select = document.getElementById("program_enrollment_id")
    select.replaceChildren()
    const empty = document.createElement("option")
    empty.value = ""
    empty.textContent = i18n("session.single_no_package")
    select.appendChild(empty)
    state.enrollments = []

    if (!clientId) {
        setText("program_progress", i18n("session.no_active_program"))
        return
    }

    const response = await fetch(
        `/api/client-programs?client_id=${encodeURIComponent(clientId)}`,
        {credentials: "same-origin"}
    )
    const enrollments = await parseJsonResponse(
        response,
        "LOAD CLIENT PROGRAMS"
    )
    if (!response.ok || !Array.isArray(enrollments)) return

    state.enrollments = sortProgramsBySize(enrollments)
    state.enrollments
        .filter(enrollment => ["active", "paused"].includes(enrollment.status))
        .forEach(enrollment => {
            const option = document.createElement("option")
            option.value = enrollment.enrollment_id
            option.dataset.status = enrollment.status
            option.dataset.protocolId = enrollment.protocol_id || ""
            const statusLabel =
                enrollment.status === "paused"
                    ? i18n("session.paused_prefix")
                    : ""
            option.textContent =
                `${statusLabel}${enrollment.program_name} | ` +
                `${enrollment.completed_sessions}/${enrollment.total_sessions}`
            select.appendChild(option)
        })

    if (preferredEnrollmentId) {
        select.value = String(preferredEnrollmentId)
    }

    if (!select.value && select.options.length > 1) {
        select.selectedIndex = 1
    }
    renderProgramProgress()
    select.onchange = renderProgramProgress
}

function renderProgramProgress() {
    const enrollmentId = Number(
        document.getElementById("program_enrollment_id")?.value
    )
    const enrollment = state.enrollments.find(
        item => Number(item.enrollment_id) === enrollmentId
    )
    renderProgramManagementControls(enrollment)

    if (!enrollment) {
        setText("program_progress", i18n("session.single_outside_package"))
        return
    }

    if (enrollment.status === "paused") {
        setText(
            "program_progress",
            i18n("chamber.program_paused", {
                name: enrollment.program_name,
                completed: enrollment.completed_sessions,
                total: enrollment.total_sessions
            }) + " " +
            i18n("session.resume_before_assigning")
        )
        return
    }

    setText(
        "program_progress",
        `${enrollment.program_name}: ` + i18n(
            "session.completed_remaining",
            {
                completed: enrollment.completed_sessions,
                total: enrollment.total_sessions,
                remaining: enrollment.remaining_sessions
            }
        )
    )
    if (enrollment.protocol_id) {
        document.getElementById("protocol_id").value = enrollment.protocol_id
        applyProtocolTimingDefaults()
        updatePressurePreview()
    }
}

function renderProgramManagementControls(enrollment) {
    const pauseButton = document.getElementById("pause_program_btn")
    const resumeButton = document.getElementById("resume_program_btn")
    const cancelButton = document.getElementById("cancel_program_btn")

    if (!pauseButton || !resumeButton || !cancelButton) {
        return
    }

    pauseButton.hidden = !enrollment || enrollment.status !== "active"
    resumeButton.hidden = !enrollment || enrollment.status !== "paused"
    cancelButton.hidden =
        !enrollment || !["active", "paused"].includes(enrollment.status)
}

async function enrollSelectedClient() {
    const clientId = getSelectedSubjectId()
    const programId = Number(
        document.getElementById("program_catalog")?.value
    )
    if (!clientId || !programId) {
        alert(i18n("chamber.select_client_program_alert"))
        return
    }
    const response = await fetch("/api/client-programs", {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            client_id: clientId,
            program_id: programId
        })
    })
    const data = await parseJsonResponse(response, "ASSIGN PACKAGE")
    if (!response.ok) {
        alert(data.error || i18n("chamber.enrollment_failed"))
        return
    }
    await loadClientPrograms(data.enrollment_id)
}

async function updateSelectedProgramStatus(status) {
    const enrollmentId = Number(
        document.getElementById("program_enrollment_id")?.value
    )
    const enrollment = state.enrollments.find(
        item => Number(item.enrollment_id) === enrollmentId
    )

    if (!enrollment) {
        alert(i18n("chamber.select_program_first"))
        return
    }

    if (
        status === "cancelled" &&
        !confirm(i18n("chamber.cancel_program_confirm", {
            name: enrollment.program_name
        }))
    ) {
        return
    }

    const response = await fetch(`/api/client-programs/${enrollmentId}`, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({status})
    })
    const data = await parseJsonResponse(response, "UPDATE CLIENT PACKAGE")

    if (!response.ok || data.error) {
        alert(data.error || i18n("chamber.program_update_failed"))
        return
    }

    await loadClientPrograms(
        status === "cancelled" ? null : enrollmentId
    )
}

function toggleDetailedTimeline() {
    const enabled = document.getElementById("use_detailed_timeline").checked
    document.getElementById("session_segments_editor").hidden = !enabled
    if (
        enabled &&
        document.getElementById("session_segments_rows").children.length === 0
    ) {
        const protocol = getSelectedProtocol()
        addSessionSegment("compression", protocol?.compression_time_min)
        addSessionSegment("exposure", protocol?.exposure_time_min)
        addSessionSegment("decompression", protocol?.decompression_time_min)
    }
    updateSegmentsTotal()
}

function addSessionSegment(phase = "exposure", duration = "") {
    const row = document.createElement("div")
    row.className = "segment-row"
    row.innerHTML = `
        <select class="segment-phase">
            <option value="compression">${escapeHtml(i18n("chamber.segment_compression"))}</option>
            <option value="exposure">${escapeHtml(i18n("chamber.segment_exposure"))}</option>
            <option value="air_break">${escapeHtml(i18n("chamber.segment_air_break"))}</option>
            <option value="decompression">${escapeHtml(i18n("chamber.segment_decompression"))}</option>
            <option value="recovery">${escapeHtml(i18n("chamber.segment_recovery"))}</option>
            <option value="other">${escapeHtml(i18n("chamber.segment_other"))}</option>
        </select>
        <input class="segment-duration" type="number" min="0" max="360"
            step="1" value="${Number(duration) || 0}" aria-label="${escapeHtml(i18n("chamber.segment_duration_min"))}">
        <input class="segment-target-ata" type="number" min="1" max="3"
            step="0.01" value="${getSelectedProtocol()?.target_ata || ""}"
            aria-label="${escapeHtml(i18n("chamber.segment_target_ata"))}">
        <input class="segment-actual-ata" type="number" min="1" max="3"
            step="0.01" placeholder="${escapeHtml(i18n("chamber.segment_actual_ata"))}" aria-label="${escapeHtml(i18n("chamber.segment_actual_ata"))}">
        <input class="segment-note" placeholder="${escapeHtml(i18n("chamber.segment_note"))}"
            aria-label="${escapeHtml(i18n("chamber.segment_note"))}">
        <button type="button" class="danger-btn" title="${escapeHtml(i18n("chamber.remove_segment"))}">×</button>
    `
    row.querySelector(".segment-phase").value = phase
    row.querySelector("button").onclick = () => {
        row.remove()
        updateSegmentsTotal()
    }
    row.querySelectorAll("input, select").forEach(element => {
        element.addEventListener("input", updateSegmentsTotal)
    })
    document.getElementById("session_segments_rows").appendChild(row)
    updateSegmentsTotal()
}

function collectSessionSegments() {
    if (!document.getElementById("use_detailed_timeline").checked) return []
    return [...document.querySelectorAll(".segment-row")].map(row => ({
        phase: row.querySelector(".segment-phase").value,
        actual_duration_min: Number(
            row.querySelector(".segment-duration").value
        ),
        target_ata: Number(row.querySelector(".segment-target-ata").value),
        actual_ata:
            Number(row.querySelector(".segment-actual-ata").value) || null,
        note: row.querySelector(".segment-note").value.trim() || null
    }))
}

function updateSegmentsTotal() {
    const total = collectSessionSegments().reduce(
        (sum, segment) => sum + (segment.actual_duration_min || 0),
        0
    )
    setText("segments_total", i18n("chamber.total_segments", {total}))
}

function applyProtocolTimingDefaults() {
    const protocol = getSelectedProtocol()
    const preview = document.getElementById("protocol_plan_preview")

    if (!protocol) {
        if (preview) {
            preview.textContent =
                i18n("chamber.select_protocol_timing")
        }
        return
    }

    const compression = protocolPhaseValue(
        protocol,
        "compression_time_min"
    )
    const exposure = protocolPhaseValue(protocol, "exposure_time_min")
    const decompression = protocolPhaseValue(
        protocol,
        "decompression_time_min"
    )
    const total = protocolPhaseValue(
        protocol,
        "planned_duration_min",
        compression + exposure + decompression
    )

    document.getElementById("during_compression_min").value = compression
    document.getElementById("during_exposure_min").value = exposure
    document.getElementById("during_decompression_min").value = decompression

    if (preview) {
        preview.textContent = i18n("chamber.plan_preview", {
            compression,
            exposure,
            decompression,
            total
        })
    }
    updateDurationPreview()
}

function getSelectedChamber() {
    const chamberId =
        Number(document.getElementById("chamber_id")?.value)

    return state.chambers.find(
        chamber => Number(chamber.chamber_id) === chamberId
    ) || null
}

function updatePressurePreview() {
    const preview = document.getElementById("ata_preview")
    const pressureValue =
        document.getElementById("during_pressure")?.value
    const pressureUnit =
        document.getElementById("during_pressure_unit")?.value ||
        DEFAULT_PRESSURE_INPUT_UNIT
    const actualAta = pressureToAta(pressureValue, pressureUnit)
    const selectedProtocol = getSelectedProtocol()

    if (!preview) return

    if (!selectedProtocol) {
        preview.textContent = i18n("chamber.select_protocol")
        return
    }

    const targetAta = Number(selectedProtocol.target_ata)

    if (actualAta === null) {
        preview.textContent = i18n("chamber.pressure_target_enter", {
            target: targetAta.toFixed(2)
        })
        return
    }

    const difference = actualAta - targetAta
    const differenceLabel =
        `${difference >= 0 ? "+" : ""}${difference.toFixed(3)} ATA`

    preview.textContent = i18n("chamber.pressure_preview", {
        target: targetAta.toFixed(2),
        recorded: actualAta.toFixed(3),
        difference: differenceLabel
    })
}

async function loadSessionConfiguration() {
    try {
        const [chambersResponse, protocolsResponse] = await Promise.all([
            fetch("/api/chambers", {credentials: "same-origin"}),
            fetch("/api/protocols", {credentials: "same-origin"})
        ])
        const chambers = await parseJsonResponse(
            chambersResponse,
            "LOAD CHAMBERS"
        )
        const protocols = await parseJsonResponse(
            protocolsResponse,
            "LOAD PROTOCOLS"
        )

        if (!chambersResponse.ok || !Array.isArray(chambers)) {
            throw new Error(chambers.error || "Cannot load chambers")
        }
        if (!protocolsResponse.ok || !Array.isArray(protocols)) {
            throw new Error(protocols.error || "Cannot load protocols")
        }

        state.chambers = chambers
        state.protocols = protocols

        const chamberSelect = document.getElementById("chamber_id")
        const protocolSelect = document.getElementById("protocol_id")

        chamberSelect.replaceChildren()
        chambers.forEach(chamber => {
            const option = document.createElement("option")
            option.value = chamber.chamber_id
            option.textContent = chamber.location
                ? `${chamber.name} · ${chamber.location}`
                : chamber.name
            chamberSelect.appendChild(option)
        })

        protocolSelect.replaceChildren()
        const placeholder = document.createElement("option")
        placeholder.value = ""
        placeholder.textContent = i18n("chamber.select_protocol")
        protocolSelect.appendChild(placeholder)

        protocols.forEach(protocol => {
            const option = document.createElement("option")
            option.value = protocol.protocol_id
            option.textContent =
                i18n("chamber.protocol_option", {
                    name: protocol.name,
                    minutes: protocol.planned_duration_min || "-"
                })
            protocolSelect.appendChild(option)
        })
        const preferredProtocol = protocols.find(
            protocol => protocol.code === "WELLNESS_1_5"
        )
        if (preferredProtocol) {
        protocolSelect.value = preferredProtocol.protocol_id
        applyProtocolTimingDefaults()
        }

        const pressureUnitInput =
            document.getElementById("during_pressure_unit")
        if (pressureUnitInput) {
            pressureUnitInput.value = DEFAULT_PRESSURE_INPUT_UNIT
        }

        chamberSelect.addEventListener("change", () => {
            const pressureUnitInput =
                document.getElementById("during_pressure_unit")
            if (pressureUnitInput) {
                pressureUnitInput.value = DEFAULT_PRESSURE_INPUT_UNIT
            }
            updatePressurePreview()
        })
        protocolSelect.addEventListener("change", () => {
            applyProtocolTimingDefaults()
            updatePressurePreview()
        })
        ;[
            "during_compression_min",
            "during_exposure_min",
            "during_decompression_min"
        ].forEach(id => {
            document.getElementById(id)?.addEventListener(
                "input",
                updateDurationPreview
            )
        })
        applyProtocolTimingDefaults()
        updatePressurePreview()
    } catch (error) {
        console.error("Session configuration load failed:", error)
        setText("ata_preview", i18n("chamber.config_unavailable"))
    }
}

function initOxygenPreview() {

    const oxygen =
        document.getElementById("during_oxygen_lpm")
    const percent =
        document.getElementById("during_oxygen_percent")

    if (!oxygen) return

    const renderRecordedOxygen = () => {
        const lpm = parseLocalizedNumber(oxygen.value)
        const calculatedPercent = flowToConcentratorOxygenPercent(lpm)

        if (
            percent &&
            calculatedPercent !== null &&
            (
                !percent.value ||
                percent.dataset.autoCalculated === "true"
            )
        ) {
            percent.value = calculatedPercent.toFixed(1)
            percent.dataset.autoCalculated = "true"
        }

        const oxygenPercent = parseLocalizedNumber(percent?.value)
        const values = []

        if (Number.isFinite(lpm) && lpm > 0) {
            values.push(`${lpm.toFixed(1)} L/min`)
        }
        if (Number.isFinite(oxygenPercent) && oxygenPercent > 0) {
            values.push(i18n("chamber.mask_o2_value", {
                value: oxygenPercent.toFixed(1)
            }))
        }

        document.getElementById("oxygen_preview").innerText =
            values.length
                ? i18n("chamber.recorded_values", {
                    values: values.join(" | ")
                })
                : i18n("chamber.oxygen_preview_empty")
    }

    oxygen.addEventListener("input", renderRecordedOxygen)
    percent?.addEventListener("input", () => {
        percent.dataset.autoCalculated = "false"
        renderRecordedOxygen()
    })
    renderRecordedOxygen()
}

function flowToConcentratorOxygenPercent(flowValue) {
    const flow = parseLocalizedNumber(flowValue)

    if (!Number.isFinite(flow) || flow <= 0) {
        return null
    }

    const boundedFlow = Math.min(
        CONCENTRATOR_MAX_FLOW_LPM,
        Math.max(CONCENTRATOR_MIN_FLOW_LPM, flow)
    )
    const flowRatio =
        (boundedFlow - CONCENTRATOR_MIN_FLOW_LPM) /
        (CONCENTRATOR_MAX_FLOW_LPM - CONCENTRATOR_MIN_FLOW_LPM)

    return (
        CONCENTRATOR_MIN_OXYGEN_PERCENT +
        flowRatio * (
            CONCENTRATOR_MAX_OXYGEN_PERCENT -
            CONCENTRATOR_MIN_OXYGEN_PERCENT
        )
    )
}

// ========================================
// NAVIGATION
// ========================================

function go(phase) {

    if (
        phase === "during" &&
        !state.pre?.saved
    ) {
        alert(i18n("chamber.save_check_in_first"))
        return
    }

    if (
        phase === "post" &&
        !state.during?.saved
    ) {
        alert(i18n("chamber.save_session_first"))
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
        normalizeSubjectId(
            document.getElementById("subject_id").value
        )

    if (!subjectId) {
        alert(i18n("chamber.enter_client_id"))
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

        alert(data.error || i18n("chamber.create_client_failed"))
        return
    }

    alert(i18n("chamber.client_created"))

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
        alert(i18n("chamber.no_client_selected"))
        return
    }

    if (!confirm(i18n("chamber.delete_client_confirm", {
        client: subjectLabel,
        id: subjectId
    }))) {
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
            alert(i18n("chamber.backend_html_response"))
            return
        }

        if (!res.ok || data.error) {
            alert(data.error || i18n("chamber.delete_client_failed"))
            return
        }

        alert(i18n("chamber.client_deleted"))

        loadSubjects()

        if (typeof loadSessions === "function") {
            loadSessions()
        }

    } catch (err) {

        console.error("deleteSubject crash:", err)

        alert(i18n("chamber.delete_client_crashed"))
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
        s.is_active !== false &&
        s.subject_id &&
        !looksLikeGeneratedSessionId(s.subject_id) &&
        !looksLikeGeneratedSessionId(s.user_id) &&
        !s.email &&
        s.role !== "admin" &&
        s.role !== "researcher"
    )

    console.log("LOAD SUBJECTS all:", subjects)
    console.log("LOAD SUBJECTS filtered:", onlySubjects)

    onlySubjects.forEach(subject => {

        const value =
            normalizeSubjectId(
                subject.user_id || subject.subject_id
            )

        const label =
            normalizeSubjectId(
                subject.subject_id || subject.user_id
            )

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
        getSelectedSubjectId()

    if (!subject) return

    document.getElementById(
        "session_id"
    ).value =
        `${subject}_${Date.now()}`

    state = {
        pre: null,
        during: null,
        post: null,
        chambers: state.chambers || [],
        protocols: state.protocols || [],
        programs: state.programs || [],
        enrollments: []
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

    loadClientPrograms()
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

        alert(i18n("chamber.fill_check_in"))
        return
    }

    const checkIn = collectPreCheckIn()

    try {

        state.pre = {

            saved: true,

            phase: "pre",

            spo2: spo2,

            pulse: pulse,

            check_in: checkIn
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
                        getSelectedSubjectId(),

                    phase: "pre",

                    spo2: spo2,

                    pulse: pulse,

                    check_in: checkIn
                })
            }
        )

    const data = await parseJsonResponse(res, "SAVE PRE")

        if (!res.ok || data.error) {

            state.pre = null

            alert(
                data.error ||
                i18n("chamber.check_in_save_failed")
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

                <b>${escapeHtml(i18n("chamber.check_in_saved"))}</b>

                <br><br>

                Session:
                ${document.getElementById("session_id").value}

                <br>

                SpO2:
                ${spo2}%

                <br>

                Pulse:
                ${pulse} bpm

                <br><br>

                <b>Check-in context</b><br>
                ${contextPreview(checkIn)}

            </div>
        `

        requestAnimationFrame(() => {

            requestAnimationFrame(() => {

                go("during")

            })

        })

        alert(i18n("chamber.check_in_saved_success"))

    } catch (err) {

        console.error(err)

        state.pre = null

        alert(i18n("chamber.check_in_server_error"))
    }
}

// ========================================
// HR / HRV timeline upload (FIT parser under the hood)
// ========================================

async function uploadFIT() {

    let input =
        document.getElementById("fitFile")

    const status =
        document.getElementById("fitStatus")

    const uploadButton =
        document.getElementById("uploadFitButton")

    if (!input.files.length) {

        alert(i18n("chamber.select_hr_file"))
        return
    }

    let file = input.files[0]
    const sessionId =
        document.getElementById("session_id").value.trim()

    if (!sessionId) {

        alert(i18n("chamber.generate_session_first"))
        return
    }

    let fd = new FormData()

    fd.append("file", file)

    fd.append(
        "session_id",
        sessionId
    )
    fd.append(
        "client_id",
        getSelectedSubjectId()
    )

    const selectedDevice = getSelectedCompatibilityDevice()
    if (selectedDevice) {
        fd.append("device_model", selectedDevice.model)
    }

    try {

        if (uploadButton) {
            uploadButton.disabled = true
        }

        if (status) {
            status.innerHTML = `
                <div class="success-box">
                    ${escapeHtml(i18n("chamber.uploading_hr"))}
                </div>
            `
        }

        const controller = new AbortController()
        const timeoutId = setTimeout(
            () => controller.abort(),
            FIT_UPLOAD_TIMEOUT_MS
        )

        let res

        try {
            res = await fetch(
                "/upload_fit",
                {
                    method: "POST",
                    credentials: "same-origin",
                    body: fd,
                    signal: controller.signal
                }
            )
        } finally {
            clearTimeout(timeoutId)
        }

        let data = await parseJsonResponse(res, "UPLOAD HR/HRV TIMELINE")
        const duplicateImport =
            res.status === 409 &&
            data &&
            data.status === "duplicate" &&
            data.import_type === "fit"

        if ((!res.ok && !duplicateImport) || (data.error && !duplicateImport)) {

            console.error(data)

            alert(
                data.error ||
                i18n("chamber.hr_upload_failed")
            )

            if (status) {
                status.innerHTML = `
                    <div class="error-box">
                        ${escapeHtml(data.error || i18n("chamber.hr_upload_failed"))}
                    </div>
                `
            }

            return
        }

        if (status) {
            const fitStatusMessage =
                duplicateImport
                    ? i18n("chamber.hr_timeline_already_imported")
                    : i18n("chamber.hr_timeline_uploaded")

            status.innerHTML = `

            <div class="success-box">

                ${escapeHtml(fitStatusMessage)}

                <br>

                ${escapeHtml(i18n("chamber.records_count", {
                    count: data.records_saved || data.records || 0
                }))}

            </div>
            `
        }

        await loadFITTable(sessionId, data.import_id)
        clearMergedPreview()

        if (typeof loadFitChart === "function") {

            loadFitChart(sessionId, data.import_id)
        }
        await loadSessionDataSources()

    } catch (err) {

        console.error(err)

        const message =
            err.name === "AbortError"
                ? i18n("chamber.hr_upload_timeout")
                : i18n("chamber.hr_upload_server_error")

        if (status) {
            status.innerHTML = `
                <div class="error-box">
                    ${message}
                </div>
            `
        }

        alert(message)

    } finally {

        if (uploadButton) {
            uploadButton.disabled = false
        }
    }
}

function getSelectedCompatibilityDevice() {
    const selectedId = document.getElementById("compatibilityDevice")?.value
    return compatibilityDevices.find(device => device.id === selectedId) || null
}

function compatibilityDeviceLabel(device) {
    const manufacturer = String(device?.manufacturer || "").trim()
    const model = String(device?.model || "").trim()
    return model.toLowerCase().startsWith(manufacturer.toLowerCase())
        ? model
        : `${manufacturer} ${model}`.trim()
}

function deviceAnalysisGuidance(role) {
    const key = {
        raw_rr_when_present_and_verified: "chamber.device_analysis_raw_rr",
        watch_trend_unless_external_hrm_is_verified: "chamber.device_analysis_watch",
        reported_hrv_and_trend_only: "chamber.device_analysis_reported",
        spo2_reference_pulse_auxiliary: "chamber.device_analysis_spo2",
    }[role]
    return key ? i18n(key) : role || "-"
}

function applyDeviceCompatibility() {
    const selected = getSelectedCompatibilityDevice()
    const guidance = document.getElementById("compatibilityDeviceGuidance")
    const externalType = document.getElementById("externalTelemetryType")
    const deviceModel = document.getElementById("externalTelemetryDeviceModel")

    if (!selected) {
        if (guidance) {
            guidance.textContent = i18n("chamber.device_guidance_empty")
        }
        return
    }

    if (deviceModel) {
        deviceModel.value = compatibilityDeviceLabel(selected)
    }

    const importTypes = Array.isArray(selected.import_types)
        ? selected.import_types
        : []
    const preferredExternalType = importTypes.find(type => (
        type !== "fit" && type !== "csv"
    ))
    if (externalType && preferredExternalType) {
        externalType.value = preferredExternalType
    }

    if (!guidance) {
        return
    }

    const importMessage = importTypes.length
        ? i18n("chamber.device_import_ready", {
            formats: (selected.formats || []).join(", "),
        })
        : i18n("chamber.device_import_planned")
    guidance.innerHTML = `
        <strong>${escapeHtml(compatibilityDeviceLabel(selected))}</strong>
        <small>${escapeHtml(importMessage)}</small>
        <small>${escapeHtml(i18n("chamber.device_raw_rr", {value: selected.raw_rr || "-"}))} · ${escapeHtml(i18n("chamber.device_reported_hrv", {value: selected.reported_hrv || "-"}))}</small>
        <small>${escapeHtml(i18n("chamber.device_analysis_role", {value: deviceAnalysisGuidance(selected.analysis_role)}))} · ${escapeHtml(i18n("chamber.device_cloud", {value: selected.cloud_account || "-"}))}</small>
    `
}

async function loadDeviceCompatibility() {
    const select = document.getElementById("compatibilityDevice")
    if (!select) {
        return
    }

    try {
        const response = await fetch("/api/device-catalog", {
            credentials: "same-origin",
        })
        const data = await parseJsonResponse(response, "LOAD DEVICE COMPATIBILITY")
        if (!response.ok || !Array.isArray(data.compatibility)) {
            throw new Error(data.error || "device catalog unavailable")
        }

        compatibilityDevices = data.compatibility.slice().sort((left, right) => (
            `${left.manufacturer} ${left.model}`.localeCompare(
                `${right.manufacturer} ${right.model}`,
            )
        ))
        const selectedValue = select.value
        select.replaceChildren(new Option(
            i18n("chamber.select_device_placeholder"),
            "",
        ))
        compatibilityDevices.forEach(device => {
            select.add(new Option(
                `${device.manufacturer} ${device.model} · ${device.support_level}`,
                device.id,
            ))
        })
        select.value = selectedValue
        select.addEventListener("change", applyDeviceCompatibility)
    } catch (error) {
        console.error("Device compatibility unavailable", error)
    }
}

async function uploadExternalTelemetry() {
    const input = document.getElementById("externalTelemetryFile")
    const type = document.getElementById("externalTelemetryType")?.value
    const deviceModel = document.getElementById("externalTelemetryDeviceModel")?.value.trim()
    const timezoneInput = document.getElementById("externalTelemetryTimezone")
    const status = document.getElementById("externalTelemetryStatus")
    const sessionId = document.getElementById("session_id")?.value.trim()

    if (!input?.files.length || !type) {
        alert(i18n("chamber.select_external_telemetry"))
        return
    }
    if (!sessionId) {
        alert(i18n("chamber.generate_session_first"))
        return
    }

    const formData = new FormData()
    formData.append("file", input.files[0])
    formData.append("session_id", sessionId)
    formData.append("client_id", getSelectedSubjectId())
    formData.append("import_type", type)
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
    const selectedTimezone = timezoneInput?.value || "browser"
    const sourceTimezone = selectedTimezone === "browser" ? browserTimezone : selectedTimezone
    if (sourceTimezone && sourceTimezone !== "unknown") {
        formData.append("source_timezone", sourceTimezone)
    }
    if (deviceModel) {
        formData.append("device_model", deviceModel)
    }
    if (status) {
        status.innerHTML = `<div class="success-box">${escapeHtml(i18n("chamber.uploading_external_telemetry"))}</div>`
    }
    try {
        const response = await fetch("/upload_telemetry", {
            method: "POST",
            credentials: "same-origin",
            body: formData,
        })
        const data = await parseJsonResponse(response, "UPLOAD EXTERNAL TELEMETRY")
        const duplicate = response.status === 409 && data?.status === "duplicate"
        if ((!response.ok && !duplicate) || (data.error && !duplicate)) {
            throw new Error(data.error || i18n("chamber.external_telemetry_upload_failed"))
        }
        if (status) {
            status.innerHTML = `<div class="success-box">${escapeHtml(duplicate ? i18n("chamber.external_telemetry_already_imported") : i18n("chamber.external_telemetry_uploaded"))}<br>${escapeHtml(i18n("chamber.records_count", {count: data.records_saved || data.records || 0}))}</div>`
        }
        await loadFITTable(sessionId, data.import_id)
        clearMergedPreview()
        if (typeof loadFitChart === "function") {
            loadFitChart(sessionId, data.import_id)
        }
        await loadSessionDataSources()
    } catch (error) {
        console.error("uploadExternalTelemetry failed", error)
        if (status) {
            status.innerHTML = `<div class="error-box">${escapeHtml(error.message || error)}</div>`
        }
    }
}

function preflightConfig(kind) {
    if (kind === "fit") {
        return {input: "fitFile", output: "fitPreflight", importType: "fit"}
    }
    if (kind === "csv") {
        return {input: "csvFile", output: "csvPreflight", importType: "csv"}
    }
    return {
        input: "externalTelemetryFile",
        output: "externalTelemetryPreflight",
        importType: document.getElementById("externalTelemetryType")?.value,
    }
}

function hrvStatusLabel(status) {
    return i18n(`chamber.hrv_${status || "not_available"}`)
}

function telemetryValueLabel(value) {
    const normalized = String(value || "unknown").toLowerCase()
    const key = `chamber.value_${normalized}`
    const translated = i18n(key)
    return translated === key ? normalized : translated
}

async function preflightTelemetry(kind) {
    const config = preflightConfig(kind)
    const input = document.getElementById(config.input)
    const output = document.getElementById(config.output)
    if (!input?.files.length || !config.importType) {
        if (output) output.innerHTML = `<div class="error-box">${escapeHtml(i18n("chamber.preflight_select_file"))}</div>`
        return
    }
    const formData = new FormData()
    formData.append("file", input.files[0])
    formData.append("import_type", config.importType)
    const selected = getSelectedCompatibilityDevice()
    const model = kind === "external"
        ? document.getElementById("externalTelemetryDeviceModel")?.value.trim()
        : selected?.model
    if (model) formData.append("device_model", model)
    if (output) output.textContent = i18n("chamber.preflight_validating")
    try {
        const response = await fetch("/api/telemetry/preflight", {
            method: "POST", credentials: "same-origin", body: formData,
        })
        const data = await parseJsonResponse(response, "TELEMETRY PREFLIGHT")
        if (!response.ok || data.error) throw new Error(data.error || "Validation failed")
        const signals = Object.entries(data.signals || {})
            .filter(([, available]) => available)
            .map(([name]) => i18n(`chamber.signal_${name}`))
            .join(", ") || i18n("chamber.preflight_signals_none")
        output.innerHTML = `<div class="preflight-ready"><strong>${escapeHtml(i18n("chamber.preflight_ready"))}</strong><small>${escapeHtml(i18n("chamber.preflight_records", {valid: data.records_valid, rejected: data.records_rejected}))}</small><small>${escapeHtml(i18n("chamber.preflight_range", {start: data.first_timestamp || "-", end: data.last_timestamp || "-"}))}</small><small>${escapeHtml(i18n("chamber.preflight_signals", {signals}))}</small><small>${escapeHtml(i18n("chamber.preflight_hrv_quality", {hrv: hrvStatusLabel(data.hrv_status), quality: telemetryValueLabel(data.signal_quality)}))}</small><small>${escapeHtml(i18n("chamber.preflight_parser", {version: data.parser_version}))}</small></div>`
    } catch (error) {
        if (output) output.innerHTML = `<div class="error-box">${escapeHtml(error.message || error)}</div>`
    }
}

async function loadSessionDataSources() {
    const sessionId = document.getElementById("session_id")?.value.trim()
    const clientId = getSelectedSubjectId()
    const output = document.getElementById("sessionDataSources")
    if (!output || !sessionId || !clientId) return
    try {
        const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/data-sources?client_id=${encodeURIComponent(clientId)}`, {credentials: "same-origin"})
        const data = await parseJsonResponse(response, "SESSION DATA SOURCES")
        if (!response.ok || data.error) throw new Error(data.error || "Could not load sources")
        if (!data.sources?.length) {
            output.textContent = i18n("chamber.session_data_sources_none")
            return
        }
        output.innerHTML = `<div class="session-data-source-list">${data.sources.map(source => {
            const hrv = source.has_raw_rr ? i18n("chamber.source_hrv_from_rr") : (source.import_type === "apple_health_xml" || source.import_type === "health_connect_json" ? i18n("chamber.source_hrv_reported") : i18n("chamber.source_hrv_none"))
            const records = i18n("chamber.source_records", {start: source.first_timestamp || "-", end: source.last_timestamp || "-", count: source.records_saved || 0})
            const provenance = i18n("chamber.source_provenance", {hrv, parser: source.parser_version || "-", timezone: source.source_timezone || "unknown"})
            const audit = i18n("chamber.source_audit", {imported: source.imported_at || "-", hash: String(source.file_hash || "-").slice(0, 12)})
            return `<div class="session-data-source"><strong>${escapeHtml(source.device_model || source.import_type)}</strong><small>${escapeHtml(source.import_type)} | ${escapeHtml(source.measurement_method || "unknown")} | ${escapeHtml(source.device_type || "unknown")}</small><small>${escapeHtml(records)}</small><small>${escapeHtml(provenance)}</small><small>${escapeHtml(audit)}</small><small>${escapeHtml(i18n("chamber.source_reimport_required"))}</small></div>`
        }).join("")}</div>`
    } catch (error) {
        output.innerHTML = `<div class="error-box">${escapeHtml(error.message || error)}</div>`
    }
}

function exportClient() {
    const clientId = getSelectedSubjectId()

    if (!clientId) {
        alert(i18n("chamber.select_client_first"))
        return
    }

    window.location.href =
        "/api/clients/" +
        encodeURIComponent(clientId) +
        "/export"
}

async function loadFITTable(session, importId = null) {
    try {

    let tbody =
        document.querySelector(
            "#fitDataTable tbody"
        )

    if (!tbody) {
        return
    }

    setText("fitTableStatus", "")

    tbody.innerHTML = `
        <tr>
            <td colspan="4">
                ${escapeHtml(i18n("chamber.hr_preview_loading"))}
            </td>
        </tr>
    `

    const params = new URLSearchParams({
        session_id: session,
        limit: String(TABLE_PREVIEW_LIMIT)
    })

    if (importId) {
        params.set("import_id", String(importId))
    }

let res = await fetch(
    "/api/fit_data?" + params.toString(),
    {
        credentials: "same-origin"
    }
)

let data = await parseJsonResponse(res, "LOAD HR/HRV TIMELINE")

    if (!Array.isArray(data)) {

        console.error(data)
        setText("fitTableStatus", i18n("chamber.hr_table_invalid_response"))

        tbody.innerHTML = `
            <tr>
                <td colspan="4">
                    ${escapeHtml(i18n("chamber.hr_data_invalid"))}
                </td>
            </tr>
        `

        return
    }

    if (data.length === 0) {
        setText("fitTableStatus", i18n("chamber.hr_table_records", {count: 0}))

        tbody.innerHTML = `
            <tr>
                <td colspan="4">
                    ${escapeHtml(i18n("chamber.hr_no_records"))}
                </td>
            </tr>
        `

        return
    }

    setText(
        "fitTableStatus",
        i18n("chamber.hr_table_rendering", {count: data.length})
    )

    await renderTableRowsChunked(
        tbody,
        data,
        [
            r => displayValue(r.timestamp, r.time),
            r => displayValue(r.heart_rate, r.hr, r.pulse),
            r => displayValue(r.rr, r.rr_interval, r.rr_intervals),
            r => displayValue(r.hrv, r.rmssd)
        ]
    )

    setText(
        "fitTableStatus",
        data.length >= TABLE_PREVIEW_LIMIT
            ? i18n("chamber.hr_table_first_loaded", {count: data.length})
            : i18n("chamber.hr_table_loaded", {count: data.length})
    )

    } catch (err) {
        console.error("loadFITTable failed", err)
        setText(
            "fitTableStatus",
            i18n("chamber.hr_table_error", {error: err.message || err})
        )
    }
}

// ========================================
// SpO2 / pulse timeline upload (CSV parser under the hood)
// ========================================

async function uploadCSV() {

    let input =
        document.getElementById("csvFile")

    if (!input.files.length) {

        alert(i18n("chamber.select_spo2_file"))
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
    fd.append(
        "client_id",
        getSelectedSubjectId()
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

let data = await parseJsonResponse(res, "UPLOAD SPO2/PULSE TIMELINE")
        const duplicateImport =
            res.status === 409 &&
            data &&
            data.status === "duplicate" &&
            data.import_type === "csv"

        if ((!res.ok && !duplicateImport) || (data.error && !duplicateImport)) {

            alert(
                data.error ||
                i18n("chamber.spo2_upload_failed")
            )

            return
        }

        document.getElementById(
            "csvStatus"
        ).innerHTML = `

            <div class="success-box">

                ${escapeHtml(
                    duplicateImport
                        ? i18n("chamber.spo2_timeline_already_imported")
                        : i18n("chamber.spo2_timeline_uploaded")
                )}

                <br>

                ${escapeHtml(i18n("chamber.records_count", {
                    count: data.records_saved || data.records || 0
                }))}

            </div>
        `

        await loadCSVTable(
            document.getElementById(
                "session_id"
            ).value,
            data.import_id
        )
        await loadSessionDataSources()
        clearMergedPreview()

    } catch (err) {

        console.error(err)

        alert(i18n("chamber.spo2_upload_server_error"))
    }
}

async function loadCSVTable(session, importId = null) {
    try {

    let tbody =
        document.querySelector(
            "#csvDataTable tbody"
        )

    if (!tbody) {
        return
    }

    setText("csvTableStatus", "")

    tbody.innerHTML = `
        <tr>
            <td colspan="3">
                ${escapeHtml(i18n("chamber.spo2_preview_loading"))}
            </td>
        </tr>
    `

    const params = new URLSearchParams({
        session_id: session,
        limit: String(TABLE_PREVIEW_LIMIT)
    })

    if (importId) {
        params.set("import_id", String(importId))
    }

let res = await fetch(
    "/api/csv_data?" + params.toString(),
    {
        credentials: "same-origin"
    }
)

let data = await parseJsonResponse(res, "LOAD SPO2/PULSE TIMELINE")

    if (!Array.isArray(data)) {
        setText("csvTableStatus", i18n("chamber.spo2_table_invalid_response"))

        tbody.innerHTML = `
            <tr>
                <td colspan="3">
                    ${escapeHtml(i18n("chamber.spo2_data_invalid"))}
                </td>
            </tr>
        `

        return
    }

    if (data.length === 0) {
        setText("csvTableStatus", i18n("chamber.spo2_table_records", {count: 0}))

        tbody.innerHTML = `
            <tr>
                <td colspan="3">
                    ${escapeHtml(i18n("chamber.spo2_no_records"))}
                </td>
            </tr>
        `

        return
    }

    setText(
        "csvTableStatus",
        i18n("chamber.spo2_table_rendering", {count: data.length})
    )

    await renderTableRowsChunked(
        tbody,
        data,
        [
            r => displayValue(r.timestamp, r.time),
            r => displayValue(r.pulse, r.hr, r.heart_rate),
            r => displayValue(r.spo2, r.oxygen, r.saturation)
        ]
    )

    setText(
        "csvTableStatus",
        i18n("chamber.spo2_table_loaded", {count: data.length})
    )

    } catch (err) {
        console.error("loadCSVTable failed", err)
        setText(
            "csvTableStatus",
            i18n("chamber.spo2_table_error", {error: err.message || err})
        )
    }
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
        alert(i18n("chamber.no_session_id"))
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
                session_id: sessionId,
                client_id: getSelectedSubjectId()
            })
        })


        const data = await parseJsonResponse(res, "MERGE DURING")

        if (data.error && data.raw) {
            alert(i18n("chamber.backend_html_response"))
            return []
}

        if (!res.ok || data.error) {
            console.error("Merge backend error:", data)
            alert(data.error || i18n("chamber.merge_failed"))
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
                    HR/HRV samples: ${data.fit_samples ?? "-"}<br>
                    SpO2/pulse samples: ${data.csv_samples ?? "-"}<br>
                    ${escapeHtml(i18n("chamber.merged_samples", {count: merged.length}))}<br>
                    Matched: ${data.matched_records ?? "-"}
                    (${data.match_rate ?? "-"}%)<br>
                    HR/HRV time offset: ${data.fit_time_offset_hours ?? 0}h
                </div>
            `
        }

        console.log("MERGED:", merged)

        return merged

    } catch (err) {

        console.error("mergeDuring crash:", err)
        alert(i18n("chamber.merge_crashed"))
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

    const previewRows = rows.slice(0, 500)

    const htmlRows = previewRows.map(r => {

        const spo2 =
            r.spo2 ??
            r.SpO2 ??
            r.SO2 ??
            r.so2 ??
            r.s02 ??
            r.S02 ??
            r.sp02 ??
            "-"

        return `
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

    tbody.innerHTML = htmlRows.join("")
}


// ========================================
// DURING
// ========================================

async function saveDURING() {

    const sessionId =
        document.getElementById("session_id").value

    const subjectId =
        getSelectedSubjectId()

    const pressure =
        numericInputValue("during_pressure")
    const pressureUnit =
        document.getElementById("during_pressure_unit")?.value ||
        DEFAULT_PRESSURE_INPUT_UNIT
    const selectedProtocol = getSelectedProtocol()
    const selectedChamber = getSelectedChamber()
    const compressionTimeMin =
        Number(document.getElementById("during_compression_min").value)
    const exposureTimeMin =
        Number(document.getElementById("during_exposure_min").value)
    const decompressionTimeMin =
        Number(document.getElementById("during_decompression_min").value)
    const totalDurationMin =
        compressionTimeMin + exposureTimeMin + decompressionTimeMin
    const sessionSegments = collectSessionSegments()
    const detailedTotalDurationMin = sessionSegments.reduce(
        (sum, segment) => sum + (segment.actual_duration_min || 0),
        0
    )
    const effectiveTotalDurationMin =
        sessionSegments.length > 0
            ? detailedTotalDurationMin
            : totalDurationMin
    const executionStatus =
        document.getElementById("during_execution_status").value
    const deviationReason =
        document.getElementById("during_deviation_reason").value.trim()
    const programEnrollmentId =
        Number(document.getElementById("program_enrollment_id").value) || null
    const selectedEnrollment = state.enrollments.find(
        item => Number(item.enrollment_id) === programEnrollmentId
    )

    const temp =
        optionalNumberInput("during_temp")

    const bodyTemp =
        optionalNumberInput("during_body_temp")

    const humidity =
        optionalNumberInput("during_humidity")

    const oxygenLpm =
        optionalNumberInput("during_oxygen_lpm")

    const oxygenPercent =
        optionalNumberInput("during_oxygen_percent")

    if (!selectedChamber || !selectedProtocol) {
        alert(i18n("chamber.select_chamber_protocol"))
        return
    }

    if (selectedEnrollment && selectedEnrollment.status !== "active") {
        alert(i18n("chamber.resume_program_before_session"))
        return
    }

    if (!Number.isFinite(pressure) || pressure <= 0) {
        alert(i18n("chamber.enter_recorded_pressure"))
        return
    }

    if (
        !Number.isInteger(compressionTimeMin) ||
        compressionTimeMin < 0 ||
        !Number.isInteger(exposureTimeMin) ||
        exposureTimeMin < 1 ||
        !Number.isInteger(decompressionTimeMin) ||
        decompressionTimeMin < 0 ||
        effectiveTotalDurationMin > 360 ||
        effectiveTotalDurationMin < 1
    ) {
        alert(i18n("chamber.enter_valid_durations"))
        return
    }

    if (
        ["modified", "interrupted"].includes(executionStatus) &&
        !deviationReason
    ) {
        alert(i18n("chamber.enter_deviation_reason"))
        return
    }

    const ata = pressureToAta(pressure, pressureUnit)
    const targetAta = Number(selectedProtocol.target_ata)

    if (ata === null || ata < 1 || ata > 3) {
        alert(i18n("chamber.invalid_pressure_ata"))
        return
    }

    if (
        ata >
        Number(selectedChamber.max_ata) + PRESSURE_OPERATIONAL_TOLERANCE_ATA
    ) {
        alert(i18n("chamber.pressure_exceeds_chamber"))
        return
    }

    const fitRes =
    await fetch(
        "/api/fit_data?session_id=" + encodeURIComponent(sessionId) + "&limit=1",
        {
        credentials: "same-origin"
        }
    )

    const fit =
    await parseJsonResponse(fitRes, "DURING LOAD FIT")

    const csvRes =
    await fetch(
        "/api/csv_data?session_id=" + encodeURIComponent(sessionId) + "&limit=1",
        {
        credentials: "same-origin"
        }
    )

    const csv =
    await parseJsonResponse(csvRes, "DURING LOAD CSV")

    const hasFIT =
        fit && fit.length > 0

    const hasCSV =
        csv && csv.length > 0

    if (!hasFIT && !hasCSV) {
        alert(i18n("chamber.upload_timeline_first"))
        return
    }

    const merged =
        await mergeDuring()

    if (!merged || merged.length === 0) {
        alert(i18n("chamber.merge_empty"))
        return
    }

    const latestMerged =
        merged[merged.length - 1] || {}

    state.during = {
        saved: true,
        phase: "during",
        chamber_id: Number(selectedChamber.chamber_id),
        chamber_name: selectedChamber.name,
        protocol_id: Number(selectedProtocol.protocol_id),
        protocol_code: selectedProtocol.code,
        protocol_name: selectedProtocol.name,
        target_ata: targetAta,
        actual_ata: ata,
        pressure_deviation: ata - targetAta,
        pressure_input_value: pressure,
        pressure_input_unit: pressureUnit,
        pressure_ata: ata,
        chamber_temperature: temp,
        body_temperature: bodyTemp,
        humidity: humidity,
        oxygen_flow_lpm: oxygenLpm,
        oxygen_mask_percent: oxygenPercent,
        compression_time_min: compressionTimeMin,
        exposure_time_min: exposureTimeMin,
        decompression_time_min: decompressionTimeMin,
        total_duration_min: effectiveTotalDurationMin,
        execution_status: executionStatus,
        deviation_reason: deviationReason || null,
        program_enrollment_id: programEnrollmentId,
        segments: sessionSegments,
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
            chamber_id: Number(selectedChamber.chamber_id),
            protocol_id: Number(selectedProtocol.protocol_id),
            target_ata: targetAta,
            actual_ata: ata,
            pressure_deviation: ata - targetAta,
            pressure_input_value: pressure,
            pressure_input_unit: pressureUnit,
            pressure_ata: ata,
            chamber_temperature: temp,
            body_temperature: bodyTemp,
            humidity: humidity,
            oxygen_flow_lpm: oxygenLpm,
            oxygen_mask_percent: oxygenPercent,
            compression_time_min: compressionTimeMin,
            exposure_time_min: exposureTimeMin,
            decompression_time_min: decompressionTimeMin,
            total_duration_min: effectiveTotalDurationMin,
            execution_status: executionStatus,
            deviation_reason: deviationReason || null,
            program_enrollment_id: programEnrollmentId,
            segments: sessionSegments,
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
        alert(saveData.error || i18n("chamber.session_save_failed"))
        return
    }

    document.getElementById("preview_during").innerHTML = `
        <div class="warning-box">
            <b>${escapeHtml(i18n("chamber.session_saved"))}</b><br><br>

            ${escapeHtml(i18n("chamber.preview_chamber"))}: ${escapeHtml(selectedChamber.name)}<br>
            ${escapeHtml(i18n("chamber.preview_protocol"))}: ${escapeHtml(selectedProtocol.name)}<br>
            ${escapeHtml(i18n("chamber.preview_target_ata"))}: ${targetAta.toFixed(2)}<br>
            ${escapeHtml(i18n("chamber.preview_recorded_ata"))}: ${ata.toFixed(3)}<br>
            ${escapeHtml(i18n("chamber.preview_difference"))}: ${(ata - targetAta).toFixed(3)} ATA<br>
            ${escapeHtml(i18n("chamber.preview_session_time"))}: ${escapeHtml(i18n("chamber.minutes_total", {minutes: effectiveTotalDurationMin}))}
            (${compressionTimeMin} / ${exposureTimeMin} / ${decompressionTimeMin} min)<br>
            ${escapeHtml(i18n("chamber.preview_execution"))}: ${escapeHtml(executionStatus)}<br>
            ${escapeHtml(i18n("chamber.preview_deviation_reason"))}: ${escapeHtml(deviationReason || "-")}<br>
            ${escapeHtml(i18n("chamber.preview_temp"))}: ${temp}°C<br>
            ${escapeHtml(i18n("chamber.preview_o2"))}: ${oxygenPercent || "-"}%<br><br>

            ${escapeHtml(i18n("chamber.preview_hr_samples"))}: ${hasFIT ? fit.length : 0}<br>
            ${escapeHtml(i18n("chamber.preview_spo2_samples"))}: ${hasCSV ? csv.length : 0}<br>
            ${escapeHtml(i18n("chamber.preview_merged_samples"))}: ${merged.length}
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

    alert(i18n("chamber.session_saved"))
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

        alert(i18n("session.fill_recovery_data"))
        return
    }

    const checkOut = collectPostCheckOut()

    state.post = {

        saved: true,

        phase: "post",

        spo2: spo2,

        pulse: pulse,

        check_out: checkOut
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
                    getSelectedSubjectId(),

                phase: "post",

                spo2: spo2,

                pulse: pulse,

                check_out: checkOut
            })
        }
    )

    const data = await parseJsonResponse(res, "SAVE POST")

    if (!res.ok || data.error) {
        console.error("POST save error:", data)
        alert(data.error || i18n("session.recovery_save_failed"))
        return []
    }


    document.getElementById(
        "preview_post"
    ).innerHTML = `

        <div class="success-box">

            ${i18n("session.recovery_saved")}

            <br><br>

            SpO2:
            ${spo2}%

            <br>

            Pulse:
            ${pulse} bpm

            <br><br>

            <b>Check-out context</b><br>
            ${contextPreview(checkOut)}

        </div>
    `

    document
        .getElementById("step_post")
        .classList.add("done")

    updateProgress()

    // await saveFullSession()

    alert(i18n("session.recovery_saved"))
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
        alert(i18n("session.complete_all_phases"))
        return
    }

    const wellnessConsent =
        document.getElementById("wellness_consent")

    if (!wellnessConsent?.checked) {
        alert(i18n("chamber.confirm_wellness_consent"))
        return
    }

    const subjectSelect =
        document.getElementById("user_id")

    const selectedSubjectLabel =
        subjectSelect.options[subjectSelect.selectedIndex]?.text ||
        subjectSelect.value

    const payload = {
        session_id: document.getElementById("session_id").value,
        client_id: getSelectedSubjectId(),
        user_id: getSelectedSubjectId(),
        pre: {
            ...state.pre,
            wellness_consent: {
                accepted: true,
                recorded_at: new Date().toISOString()
            }
        },
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
            alert(i18n("chamber.save_full_html_response"))
            return
        }

        // alert(JSON.stringify(data))

        console.log("SAVE FULL RESPONSE:", data)

        if (!res.ok || data.error) {
            alert(data.error || i18n("chamber.save_failed"))
            return
        }

        if (data.saved_count !== 1) {
            alert(i18n("chamber.backend_save_not_confirmed", {
                count: data.saved_count
            }))
            return
        }

        document.getElementById("preview_full").innerHTML = `
            <div class="success-box">
                <b>✔ FULL SESSION SAVED</b><br><br>
                Session: ${payload.session_id}<br>
                Client: ${selectedSubjectLabel}<br>
                DB saved_count: ${data.saved_count}
            </div>
        `

        await loadSessions()

        try {
            await runAnalysis(payload.session_id)
        } catch (aiErr) {
            console.error("AI after save failed:", aiErr)
        }

        alert(i18n("chamber.full_session_saved"))

    } catch (err) {

        console.error("saveFullSession error:", err)

        alert(i18n("chamber.network_server_error"))
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
                <td colspan="4">${escapeHtml(i18n("chamber.no_saved_sessions"))}</td>
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
                <td>${s.subject_id || s.user_id || "-"}</td>

                <td>
                    <button onclick="runAnalysis('${s.session_id}')">
                        ${escapeHtml(i18n("chamber.analyze"))}
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

        alert(i18n("chamber.no_sessions_selected"))
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
    alert(data.error || i18n("chamber.delete_sessions_failed"))
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
        alert(i18n("chamber.ai_html_response"))
        return
}

        console.log("AI RESPONSE:", data)

        if (!res.ok || data.error) {
            alert(data.error || i18n("chamber.ai_failed"))
            return
        }

        const sessionFlagText =
            data.anomaly
                ? i18n("analysis.review_recommended")
                : i18n("analysis.no_session_quality_flag")

        const aiSummary =
            document.getElementById("ai-summary")

        if (aiSummary) {
            aiSummary.innerHTML =
                `<b>${escapeHtml(i18n("analysis.summary"))}:</b> ` +
                escapeHtml(translateAnalysisText(data.summary || "-"))
        }

        const aiScore =
            document.getElementById("ai-score")

        if (aiScore) {
            aiScore.innerHTML =
                `<b>${escapeHtml(i18n("analysis.wellness_response"))}:</b> ` +
                escapeHtml(data.score ?? "-") +
                " / 100"
        }

        const aiAnomaly =
            document.getElementById("ai-anomaly")

        if (aiAnomaly) {
            aiAnomaly.innerHTML =
                `<b>${escapeHtml(i18n("analysis.data_quality"))}:</b> ` +
                escapeHtml(data.data_quality_score ?? "-") +
                ` / 100 · <b>${escapeHtml(i18n("analysis.session_review"))}:</b> ` +
                escapeHtml(sessionFlagText)
        }

        renderAIVisualization(data)
        await updateLatestSessionInsight(data)

    } catch (err) {

        console.error("runAnalysis crash:", err)
        alert(i18n("chamber.ai_crashed"))
    }
}

// ========================================
// render AI Visualization
// ========================================

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;")
}

async function updateLatestSessionInsight(data) {
    const container = document.getElementById("liveScore")

    if (!container) {
        return
    }

    let baseline = null
    const clientId = getSelectedSubjectId()

    if (clientId) {
        try {
            const response = await fetch(
                `/api/wellness/summary/${encodeURIComponent(clientId)}`,
                { credentials: "same-origin" }
            )

            if (response.ok) {
                const summary = await parseJsonResponse(
                    response,
                    "LATEST SESSION BASELINE"
                )
                baseline = summary.baseline || null
            }
        } catch (error) {
            console.error("Baseline summary unavailable", error)
        }
    }

    const baselineSessions =
        Number(baseline?.sessions_count_30d || 0)
    const baselineConfidence =
        baselineSessions >= 14
            ? "Baseline ready"
            : baselineSessions >= 5
                ? "Early trend"
                : "Collecting data"

    container.innerHTML = `
        <div class="metric-list">
            ${renderMetricRows([
                {
                    label: "Wellness response",
                    value: data.score ?? data.overall_score,
                    unit: "/100"
                },
                {
                    label: "Data quality",
                    value: data.data_quality_score,
                    unit: "/100"
                },
                {
                    label: "Baseline confidence",
                    value: baselineConfidence
                },
                {
                    label: "Unique sessions (30d)",
                    value: baselineSessions
                }
            ])}
        </div>
    `
}

function formatMetric(value, unit = "") {
    if (value === undefined || value === null || value === "") {
        return `<span class="muted-value">${escapeHtml(i18n("analysis.not_available"))}</span>`
    }

    const suffix = unit ? ` <span class="metric-unit">${unit}</span>` : ""

    return `${escapeHtml(value)}${suffix}`
}

function formatScore(value) {
    if (value === undefined || value === null || value === "") {
        return `<span class="muted-value">${escapeHtml(i18n("analysis.pending"))}</span>`
    }

    return `${escapeHtml(value)}<span class="metric-unit">/100</span>`
}

function riskClass(label) {
    const normalized = String(label || "").toLowerCase()

    if (
        normalized.includes("high") ||
        normalized.includes("elevated") ||
        normalized.includes("obciąż")
    ) return "status-high"
    if (
        normalized.includes("moderate") ||
        normalized.includes("quality") ||
        normalized.includes("review") ||
        normalized.includes("jako") ||
        normalized.includes("przegl")
    ) return "status-moderate"

    return "status-low"
}

function renderFindingList(items, fallback, className = "") {
    const cleanItems = Array.isArray(items)
        ? items.filter(Boolean)
        : []

    if (!cleanItems.length) {
        return `<div class="empty-state">${escapeHtml(translateAnalysisText(fallback))}</div>`
    }

    return `
        <ul class="ai-finding-list ${className}">
            ${cleanItems
                .map(item => `<li>${escapeHtml(translateAnalysisText(item))}</li>`)
                .join("")}
        </ul>
    `
}

function renderMetricRows(rows) {
    return rows.map(row => `
        <div class="metric-row">
            <span>${escapeHtml(translateAnalysisText(row.label))}</span>
            <strong>${formatMetric(row.value, row.unit)}</strong>
        </div>
    `).join("")
}

function translateAnalysisText(value) {
    let text = String(value ?? "")
    const exactKeys = {
        "Wellness Response": "analysis.score_type_wellness_response",
        "Wellness response": "analysis.wellness_response",
        "Stable response": "analysis.stable_response",
        "Review recommended": "analysis.review_recommended",
        "No session quality flag": "analysis.no_session_quality_flag",
        "Elevated load": "analysis.elevated_load",
        "Review data quality": "analysis.review_data_quality",
        "Recovery trend": "analysis.recovery_trend",
        "SpO2 remained stable and within the expected range": "analysis.spo2_stable_expected",
        "Notable discrepancy between wearable heart rate and pulse oximeter pulse": "analysis.hr_pulse_discrepancy",
        "SpO2 dropped below the configured low oxygenation threshold": "analysis.spo2_low_threshold",
        "SpO2 was below the preferred wellness range": "analysis.spo2_below_preferred",
        "Average HRV was below the configured recovery threshold": "analysis.hrv_below_threshold",
        "Heart rate exceeded the configured high-load threshold": "analysis.hr_high_load_threshold",
        "No significant deviations detected.": "analysis.no_significant_deviations",
        "No critical rule-based finding was detected.": "analysis.no_critical_rule_finding",
        "No rule-based warning detected.": "analysis.no_rule_warning",
        "No additional positive findings.": "analysis.no_positive_findings",
        "Wellness-only score. Not a medical diagnosis.": "analysis.wellness_only_not_diagnosis",
        "Wellness and educational insight only. Not intended to diagnose, treat, cure, or prevent disease.": "analysis.wellness_educational_disclaimer",
        "Average SpO2": "analysis.avg_spo2",
        "Minimum SpO2": "analysis.min_spo2",
        "Maximum SpO2": "analysis.max_spo2",
        "Average pulse": "analysis.avg_pulse",
        "Pulse range": "analysis.pulse_range",
        "Average HR": "analysis.avg_hr",
        "HR range": "analysis.hr_range",
        "Average HRV": "analysis.avg_hrv",
        "HR/HRV samples": "analysis.hr_hrv_samples",
        "SpO2/pulse samples": "analysis.spo2_pulse_samples",
        "Merged samples": "analysis.merged_samples",
        "SpO2/pulse artifacts ignored": "analysis.spo2_artifacts_ignored",
        "Review context": "analysis.review_context",
        "Elevated load indicators": "analysis.elevated_load_indicators",
        "SpO2 warning": "analysis.spo2_warning",
        "HRV warning": "analysis.hrv_warning",
        "Data quality": "analysis.data_quality",
        "Baseline confidence": "analysis.baseline_confidence",
        "Unique sessions (30d)": "analysis.unique_sessions_30d",
        "Strong baseline": "analysis.strong_baseline",
        "Early trend": "analysis.early_trend",
        "Collecting data": "analysis.collecting_data"
    }

    if (exactKeys[text]) {
        return i18n(exactKeys[text])
    }

    const mismatchSummary = text.match(
        /^(.+?)\. A notable discrepancy was detected between wearable heart rate and pulse oximeter pulse, which may indicate sensor alignment, time alignment issues, or signal artifact\. The maximum observed difference was ([0-9.]+) bpm\.$/
    )
    if (mismatchSummary) {
        return `${translateAnalysisText(mismatchSummary[1])}. ${i18n("analysis.hr_pulse_discrepancy_detail", {
            difference: mismatchSummary[2]
        })}`
    }

    const mismatchOnly = text.match(
        /^A notable discrepancy was detected between wearable heart rate and pulse oximeter pulse, which may indicate sensor alignment, time alignment issues, or signal artifact\. The maximum observed difference was ([0-9.]+) bpm\.$/
    )
    if (mismatchOnly) {
        return i18n("analysis.hr_pulse_discrepancy_detail", {
            difference: mismatchOnly[1]
        })
    }

    const noContext =
        "No elevated sleep, fatigue, stress or recent activity context was flagged in the available check-in data."
    if (text === noContext) {
        return i18n("analysis.no_context_flags")
    }

    text = text.replaceAll(
        "SpO2 remained stable and within the expected range",
        i18n("analysis.spo2_stable_expected")
    )
    text = text.replace(
        /Pulse, wearable HR and HRV should be interpreted as wellness trend signals: (.*?)(?:\.(?= (?:Check-in|A notable))|\.$)/g,
        (_, details) => i18n("analysis.pulse_hrv_summary", {
            details: translateAnalysisPhysiologyDetails(details)
        })
    )
    text = text.replaceAll(noContext, i18n("analysis.no_context_flags"))
    text = text.replace(
        /Check-in context may influence today’s physiology interpretation: (.*?)(?:\.(?= (?:A notable))|\.$)/g,
        (_, details) => i18n("analysis.context_summary", {
            details: translateAnalysisContextDetails(details)
        })
    )
    text = text.replace(
        /A notable discrepancy was detected between wearable heart rate and pulse oximeter pulse, which may indicate sensor alignment, time alignment issues, or signal artifact\. The maximum observed difference was ([0-9.]+) bpm\./g,
        (_, difference) => i18n("analysis.hr_pulse_discrepancy_detail", {
            difference
        })
    )

    return text
}

function translateAnalysisPhysiologyDetails(value) {
    return String(value || "")
        .replace(
            /Pulse averaged ([0-9.]+) bpm \(range ([0-9.]+)-([0-9.]+) bpm\)/g,
            (_, avg, min, max) => i18n("analysis.phys_pulse_avg_range", {avg, min, max})
        )
        .replace(
            /wearable HR averaged ([0-9.]+) bpm \(range ([0-9.]+)-([0-9.]+) bpm\)/g,
            (_, avg, min, max) => i18n("analysis.phys_hr_avg_range", {avg, min, max})
        )
        .replace(
            /average HRV was ([0-9.]+) ms/g,
            (_, avg) => i18n("analysis.phys_avg_hrv", {avg})
        )
}

function translateAnalysisContextDetails(value) {
    return String(value || "")
        .replaceAll(
            "reduced sleep quality or short sleep",
            i18n("analysis.context_poor_sleep")
        )
        .replaceAll(
            "higher recent activity load",
            i18n("analysis.context_training_load")
        )
        .replaceAll(
            "reported stress or fatigue",
            i18n("analysis.context_stress_fatigue")
        )
        .replaceAll(
            "post-session recovery feedback improved",
            i18n("analysis.context_recovery_improved")
        )
}

function pickMetric(features, ...keys) {
    for (const key of keys) {
        const value = features[key]

        if (value !== undefined && value !== null && value !== "") {
            return value
        }
    }

    return null
}

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

    const scoreValue =
        data.score ??
        data.overall_score ??
        features.overall_score

    const riskLabel =
        data.wellness_status === "elevated_load"
            ? i18n("analysis.elevated_load")
            : data.wellness_status === "data_quality_warning"
                ? i18n("analysis.review_data_quality")
                : data.wellness_status === "recovery_trend"
                    ? i18n("analysis.recovery_trend")
                    : i18n("analysis.stable_response")

    const anomalyLabel =
        data.anomaly
            ? i18n("analysis.review_recommended")
            : i18n("analysis.no_session_quality_flag")

    const warnings =
        Array.isArray(data.reasons)
            ? data.reasons
            : []

    const positiveFindings =
        Array.isArray(data.positive_findings)
            ? data.positive_findings
            : []

    const disclaimer =
        translateAnalysisText(
            data.medical_disclaimer ||
            "Wellness-only score. Not a medical diagnosis."
        )

    const keyFinding =
        translateAnalysisText(
            data.summary ||
            warnings[0] ||
            positiveFindings[0] ||
            "No critical rule-based finding was detected."
        )

    const dataQualityScore =
        features.data_quality_score ??
        data.data_quality_score

    const scoreReference = `
        90-100 = Stable wellness response<br>
        70-89 = Review session context<br>
        below 70 = Elevated load indicators
    `

    const scoreMeaning = `
        The score starts at 100 and is reduced when rule-based wellness flags are detected:
        low SpO2, a large check-in to recovery SpO2 drop, elevated HR/pulse, or low HRV.
    `

    container.innerHTML = `
        <div class="panel">

            <h3>Automated Wellness Summary</h3>

            <table border="1" style="width:100%;">
                <tbody>

                    <tr>
                        <td><b>Score type</b></td>
                        <td>${data.score_type || "Wellness Response"}</td>
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
                        <td><b>Response status</b></td>
                        <td>${riskLabel}</td>
                    </tr>

                    <tr>
                        <td><b>Session flag</b></td>
                        <td>${anomalyLabel}</td>
                    </tr>

                    <tr>
                        <td><b>Wellness warnings</b></td>
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
                        <td>HR/HRV samples</td>
                        <td>${features.fit_samples ?? "-"}</td>
                    </tr>
                    <tr>
                        <td>SpO2/pulse samples</td>
                        <td>${features.csv_samples ?? "-"}</td>
                    </tr>
                    <tr>
                        <td>SpO2/pulse artifacts ignored</td>
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
                        <td>Avg SpO2 from SpO2/pulse timeline</td>
                        <td>${features.avg_csv_spo2 ?? "-"} %</td>
                    </tr>
                    <tr>
                        <td>Min SpO2 from SpO2/pulse timeline</td>
                        <td>${features.min_spo2 ?? "-"} %</td>
                    </tr>
                    <tr>
                        <td>Max SpO2 from SpO2/pulse timeline</td>
                        <td>${features.max_spo2 ?? "-"} %</td>
                    </tr>
                    <tr>
                        <td>Avg Pulse from SpO2/pulse timeline</td>
                        <td>${features.avg_csv_pulse ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Min Pulse from SpO2/pulse timeline</td>
                        <td>${features.min_csv_pulse ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Max Pulse from SpO2/pulse timeline</td>
                        <td>${features.max_csv_pulse ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Avg HR from HR/HRV timeline</td>
                        <td>${features.avg_fit_hr ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Min HR from HR/HRV timeline</td>
                        <td>${features.min_fit_hr ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Max HR from HR/HRV timeline</td>
                        <td>${features.max_fit_hr ?? "-"} bpm</td>
                    </tr>
                    <tr>
                        <td>Avg HRV from HR/HRV timeline</td>
                        <td>${features.avg_hrv ?? "-"} ms</td>
                    </tr>
                </tbody>
            </table>

        </div>

        <div class="panel">

            <h3>Interpretation Rules</h3>

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
                        <td>Check-in to recovery SpO2 drop</td>
                        <td>≥ 3% warning, ≥ 5% stronger warning</td>
                    </tr>
                    <tr>
                        <td>Pulse / HR load threshold</td>
                        <td>&gt; 160 bpm</td>
                    </tr>
                    <tr>
                        <td>HRV low-readiness threshold</td>
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

    container.innerHTML = `
        <section class="ai-report">
            <div class="ai-report-header">
                <div>
                    <h3>${escapeHtml(i18n("analysis.session_summary_title"))}</h3>
                    <p>${escapeHtml(translateAnalysisText(data.score_type || "Wellness response"))}</p>
                </div>
                <span class="status-badge ${riskClass(riskLabel)}">
                    ${escapeHtml(riskLabel)}
                </span>
            </div>

            <div class="ai-kpi-grid">
                <div class="ai-kpi-card">
                    <span>${escapeHtml(i18n("analysis.wellness_response"))}</span>
                    <strong>${formatScore(scoreValue)}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>${escapeHtml(i18n("analysis.session_review"))}</span>
                    <strong>${escapeHtml(anomalyLabel)}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>${escapeHtml(i18n("analysis.data_quality"))}</span>
                    <strong>${formatMetric(dataQualityScore, "/100")}</strong>
                </div>
                <div class="ai-kpi-card">
                    <span>${escapeHtml(i18n("analysis.timeline_samples"))}</span>
                    <strong>${formatMetric(timeline.length)}</strong>
                </div>
            </div>

            <div class="ai-summary-grid">
                <div class="ai-summary-card ai-summary-card-wide">
                    <h4>${escapeHtml(i18n("analysis.key_finding"))}</h4>
                    <p>${escapeHtml(keyFinding)}</p>
                </div>

                <div class="ai-summary-card">
                    <h4>${escapeHtml(i18n("analysis.warnings"))}</h4>
                    ${renderFindingList(
                        warnings,
                        "No rule-based warning detected.",
                        warnings.length ? "warning-list" : ""
                    )}
                </div>

                <div class="ai-summary-card">
                    <h4>${escapeHtml(i18n("analysis.positive_findings"))}</h4>
                    ${renderFindingList(
                        positiveFindings,
                        "No additional positive findings."
                    )}
                </div>

                <div class="ai-summary-card">
                    <h4>${escapeHtml(i18n("analysis.signal_quality"))}</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            {
                                label: "HR/HRV samples",
                                value: pickMetric(
                                    features,
                                    "fit_samples",
                                    "samples_total"
                                ) ?? data.fit_samples
                            },
                            {
                                label: "SpO2/pulse samples",
                                value: pickMetric(
                                    features,
                                    "csv_samples",
                                    "samples_synchronized"
                                ) ?? data.csv_samples
                            },
                            {
                                label: "Merged samples",
                                value: pickMetric(
                                    features,
                                    "merged_samples",
                                    "samples_synchronized"
                                ) ?? data.merged_samples
                            },
                            {
                                label: "SpO2/pulse artifacts ignored",
                                value: features.csv_pulse_artifacts ?? 0
                            }
                        ])}
                    </div>
                </div>

                <div class="ai-summary-card">
                    <h4>${escapeHtml(i18n("analysis.physiology_metrics"))}</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            {
                                label: "Average SpO2",
                                value: pickMetric(
                                    features,
                                    "avg_csv_spo2",
                                    "avg_spo2"
                                ),
                                unit: "%"
                            },
                            {
                                label: "Minimum SpO2",
                                value: features.min_spo2,
                                unit: "%"
                            },
                            {
                                label: "Maximum SpO2",
                                value: features.max_spo2,
                                unit: "%"
                            },
                            {
                                label: "Average pulse",
                                value: pickMetric(
                                    features,
                                    "avg_csv_pulse",
                                    "avg_pulse"
                                ),
                                unit: "bpm"
                            },
                            {
                                label: "Pulse range",
                                value: (
                                    pickMetric(
                                        features,
                                        "min_csv_pulse",
                                        "min_pulse"
                                    ) !== null &&
                                    pickMetric(
                                        features,
                                        "max_csv_pulse",
                                        "max_pulse"
                                    ) !== null
                                )
                                    ? `${
                                        pickMetric(
                                            features,
                                            "min_csv_pulse",
                                            "min_pulse"
                                        )
                                    }-${
                                        pickMetric(
                                            features,
                                            "max_csv_pulse",
                                            "max_pulse"
                                        )
                                    }`
                                    : null,
                                unit: "bpm"
                            },
                            {
                                label: "Average HR",
                                value: pickMetric(
                                    features,
                                    "avg_fit_hr",
                                    "avg_heart_rate"
                                ),
                                unit: "bpm"
                            },
                            {
                                label: "HR range",
                                value: (
                                    pickMetric(
                                        features,
                                        "min_fit_hr",
                                        "min_heart_rate"
                                    ) !== null &&
                                    pickMetric(
                                        features,
                                        "max_fit_hr",
                                        "max_heart_rate"
                                    ) !== null
                                )
                                    ? `${
                                        pickMetric(
                                            features,
                                            "min_fit_hr",
                                            "min_heart_rate"
                                        )
                                    }-${
                                        pickMetric(
                                            features,
                                            "max_fit_hr",
                                            "max_heart_rate"
                                        )
                                    }`
                                    : null,
                                unit: "bpm"
                            },
                            {
                                label: "Average HRV",
                                value: features.avg_hrv,
                                unit: "ms"
                            }
                        ])}
                    </div>
                </div>

                <div class="ai-summary-card">
                    <h4>${escapeHtml(i18n("analysis.rule_reference"))}</h4>
                    <div class="metric-list">
                        ${renderMetricRows([
                            {
                                label: "Stable response",
                                value: "90-100"
                            },
                            {
                                label: "Review context",
                                value: "70-89"
                            },
                            {
                                label: "Elevated load indicators",
                                value: i18n("analysis.below_70")
                            },
                            {
                                label: "SpO2 warning",
                                value: i18n("analysis.below_94_percent")
                            },
                            {
                                label: "HRV warning",
                                value: i18n("analysis.below_30_ms")
                            }
                        ])}
                    </div>
                </div>
            </div>

            <p class="ai-disclaimer">${escapeHtml(disclaimer)}</p>
        </section>

        <div class="panel chart-box ai-chart-box">
            <h3>${escapeHtml(i18n("analysis.ai_timeline"))}</h3>
            <canvas id="aiTimelineChart"></canvas>
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
                        label: "SpO2 from SpO2/pulse timeline",
                        data: spo2,
                        borderColor: "#F59F35",
                        backgroundColor: "#F59F35",
                        borderWidth: 1.8,
                        pointRadius: 0,
                        yAxisID: "ySpo2",
                        spanGaps: true
                    },
                    {
                        label: "Pulse from SpO2/pulse timeline",
                        data: pulse,
                        borderColor: "#F05A7E",
                        backgroundColor: "#F05A7E",
                        borderWidth: 1.8,
                        pointRadius: 0,
                        yAxisID: "yVitals",
                        spanGaps: true
                    },
                    {
                        label: "HR from HR/HRV timeline",
                        data: heartRate,
                        borderColor: "#2F9EED",
                        backgroundColor: "#2F9EED",
                        borderWidth: 1.8,
                        pointRadius: 0,
                        yAxisID: "yVitals",
                        spanGaps: true
                    },
                    {
                        label: "HRV from HR/HRV timeline",
                        data: hrv,
                        borderColor: "#FFD05A",
                        backgroundColor: "#FFD05A",
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
                            color: "rgba(226, 232, 240, 0.76)",
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
                            color: "rgba(226, 232, 240, 0.76)",
                            maxTicksLimit: 9,
                            maxRotation: 0,
                            callback: (_value, index) => {
                                const date = new Date(labels[index])

                                if (Number.isNaN(date.getTime())) {
                                    return labels[index] || ""
                                }

                                return date.toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit"
                                })
                            }
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
                            color: "rgba(226, 232, 240, 0.76)"
                        },
                        ticks: {
                            color: "rgba(226, 232, 240, 0.76)"
                        },
                        grid: {
                            color: "rgba(148, 163, 184, 0.14)"
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
                            color: "#F59F35"
                        },
                        ticks: {
                            color: "#F59F35"
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
                            color: "#FFD05A"
                        },
                        ticks: {
                            color: "#FFD05A"
                        },
                        grid: {
                            drawOnChartArea: false
                        }
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

window.createSubject = createSubject
window.deleteSubject = deleteSubject
window.loadSubjects = loadSubjects
window.generateSession = generateSession
window.exportClient = exportClient
window.enrollSelectedClient = enrollSelectedClient
window.updateSelectedProgramStatus = updateSelectedProgramStatus
window.addSessionSegment = addSessionSegment

window.savePRE = savePRE
window.uploadFIT = uploadFIT
window.uploadExternalTelemetry = uploadExternalTelemetry
window.uploadCSV = uploadCSV
window.preflightTelemetry = preflightTelemetry
window.loadSessionDataSources = loadSessionDataSources
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
