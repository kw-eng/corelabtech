"use strict";

/**
 * CoreLabTech Telemetry Intelligence
 *
 * Warstwa prezentacyjna odpowiedzialna za wyświetlanie:
 * - rozpoznanych sygnałów fizjologicznych,
 * - jakości danych,
 * - dostępnych analiz,
 * - rekomendowanego następnego kroku.
 *
 * Moduł nie eksponuje marek ani modeli urządzeń.
 * Pracuje wyłącznie na możliwościach wykrytych w danych.
 */

(function initializeTelemetryIntelligence(global) {
    const DEFAULT_TARGETS = Object.freeze({
        capabilities: "telemetry_capabilities",
        quality: "telemetry_quality",
        analysis: "analysis_availability",
        recommendation: "telemetry_recommendation",
    });

    const SIGNAL_LABELS = Object.freeze({
        timestamp: {
            pl: "Znaczniki czasu",
            en: "Timestamps",
        },
        heart_rate: {
            pl: "Tętno",
            en: "Heart rate",
        },
        pulse: {
            pl: "Puls",
            en: "Pulse",
        },
        rr_intervals: {
            pl: "Interwały RR",
            en: "RR intervals",
        },
        reported_hrv: {
            pl: "Raportowane HRV",
            en: "Reported HRV",
        },
        hrv: {
            pl: "HRV",
            en: "HRV",
        },
        spo2: {
            pl: "SpO₂",
            en: "SpO₂",
        },
        motion: {
            pl: "Ruch",
            en: "Motion",
        },
        temperature: {
            pl: "Temperatura",
            en: "Temperature",
        },
        respiration: {
            pl: "Oddech",
            en: "Respiration",
        },
        pressure: {
            pl: "Ciśnienie",
            en: "Pressure",
        },
        session_markers: {
            pl: "Etapy sesji",
            en: "Session markers",
        },
    });

    const ANALYSIS_LABELS = Object.freeze({
        heart_rate_analysis: {
            pl: "Analiza tętna",
            en: "Heart-rate analysis",
        },
        pulse_analysis: {
            pl: "Analiza pulsu",
            en: "Pulse analysis",
        },
        hrv_analysis: {
            pl: "Analiza HRV",
            en: "HRV analysis",
        },
        oxygen_analysis: {
            pl: "Analiza natlenienia",
            en: "Oxygen analysis",
        },
        time_merge: {
            pl: "Synchronizacja w czasie",
            en: "Time synchronization",
        },
        recovery_analysis: {
            pl: "Analiza recovery",
            en: "Recovery analysis",
        },
        session_context_analysis: {
            pl: "Analiza kontekstu sesji",
            en: "Session-context analysis",
        },
        ai_summary: {
            pl: "Podsumowanie AI",
            en: "AI summary",
        },
        hbot_response_score: {
            pl: "Ocena odpowiedzi na sesję",
            en: "Session response score",
        },
        longitudinal_analysis: {
            pl: "Analiza trendów",
            en: "Longitudinal analysis",
        },
        pdf_report: {
            pl: "Raport PDF",
            en: "PDF report",
        },
        full_session_analysis: {
            pl: "Pełna analiza sesji",
            en: "Full session analysis",
        },
    });

    const SOURCE_LABELS = Object.freeze({
        wearable_telemetry: {
            pl: "Telemetria HR/RR",
            en: "HR/RR telemetry",
        },
        pulse_oximetry: {
            pl: "Telemetria SpO₂ i pulsu",
            en: "SpO₂ and pulse telemetry",
        },
        session_telemetry: {
            pl: "Telemetria sesji",
            en: "Session telemetry",
        },
        external_telemetry: {
            pl: "Zewnętrzna telemetria",
            en: "External telemetry",
        },
    });

    const QUALITY_LABELS = Object.freeze({
        excellent: {
            pl: "Doskonała",
            en: "Excellent",
        },
        good: {
            pl: "Dobra",
            en: "Good",
        },
        fair: {
            pl: "Średnia",
            en: "Fair",
        },
        poor: {
            pl: "Niska",
            en: "Poor",
        },
        not_available: {
            pl: "Brak danych",
            en: "Not available",
        },
    });

    const CONFIDENCE_LABELS = Object.freeze({
        high: {
            pl: "Wysoka",
            en: "High",
        },
        medium: {
            pl: "Średnia",
            en: "Medium",
        },
        low: {
            pl: "Niska",
            en: "Low",
        },
        not_available: {
            pl: "Nieokreślona",
            en: "Not determined",
        },
    });

    /**
     * Renderuje cały panel Telemetry Intelligence.
     *
     * Obsługiwane wejścia:
     * - bezpośredni raport telemetryczny,
     * - pełna odpowiedź API z polem telemetry_intelligence.
     */
    function renderTelemetryIntelligence(input, options = {}) {
        const report = normalizeReport(input);
        const targets = resolveTargets(options);

        if (!hasReportData(report)) {
            renderEmptyState(targets);
            return;
        }

        renderTelemetryCapabilities(
            report,
            targets.capabilities,
        );

        renderTelemetryQuality(
            report,
            targets.quality,
        );

        renderAnalysisAvailability(
            report,
            targets.analysis,
        );

        renderTelemetryRecommendation(
            report,
            targets.recommendation,
        );
    }

    /**
     * Renderuje informacje o źródle i wykrytych sygnałach.
     */
    function renderTelemetryCapabilities(
        input,
        target = DEFAULT_TARGETS.capabilities,
    ) {
        const report = normalizeReport(input);
        const element = resolveElement(target);

        if (!element) {
            return;
        }

        const file = asObject(report.file);
        const signals = asObject(report.signals);

        const signalEntries = Object.entries(signals)
            .filter(([key]) => key !== "hrv");

        const availableCount = signalEntries.filter(
            ([, available]) => Boolean(available),
        ).length;

        const fileType = file.type || "—";
        const sourceType = translateDictionaryValue(
            SOURCE_LABELS,
            file.source_type || "external_telemetry",
        );

        const coverage = formatDuration(
            file.coverage_seconds,
        );

        const records = formatInteger(
            file.records,
        );

        element.innerHTML = `
            <section class="telemetry-intelligence-card">
                <div class="telemetry-card-heading">
                    <div>
                        <small>
                            ${escapeHtml(translate(
                                "Automatyczne rozpoznawanie danych",
                                "Automatic data detection",
                            ))}
                        </small>

                        <h4>
                            ${escapeHtml(translate(
                                "Wykryte sygnały",
                                "Detected signals",
                            ))}
                        </h4>
                    </div>

                    <span
                        class="telemetry-status-badge telemetry-status-ready"
                        title="${escapeHtml(translate(
                            "Liczba dostępnych sygnałów",
                            "Number of available signals",
                        ))}"
                    >
                        ${availableCount}/${signalEntries.length}
                    </span>
                </div>

                <div class="telemetry-source-summary">
                    ${renderSummaryMetric(
                        translate("Format pliku", "File format"),
                        fileType,
                    )}

                    ${renderSummaryMetric(
                        translate("Rodzaj źródła", "Source type"),
                        sourceType,
                    )}

                    ${renderSummaryMetric(
                        translate("Zakres czasu", "Time coverage"),
                        coverage,
                    )}

                    ${renderSummaryMetric(
                        translate("Liczba rekordów", "Records"),
                        records,
                    )}
                </div>

                ${
                    signalEntries.length
                        ? `
                            <div class="telemetry-capability-grid">
                                ${signalEntries.map(
                                    ([key, available]) => (
                                        renderCapabilityItem(
                                            translateDictionaryValue(
                                                SIGNAL_LABELS,
                                                key,
                                            ),
                                            Boolean(available),
                                        )
                                    ),
                                ).join("")}
                            </div>
                        `
                        : renderInlineEmptyState(
                            translate(
                                "Nie wykryto informacji o sygnałach.",
                                "No signal information was detected.",
                            ),
                        )
                }
            </section>
        `;
    }

    /**
     * Renderuje ocenę jakości danych.
     */
    function renderTelemetryQuality(
        input,
        target = DEFAULT_TARGETS.quality,
    ) {
        const report = normalizeReport(input);
        const element = resolveElement(target);

        if (!element) {
            return;
        }

        const quality = asObject(report.quality);
        const score = toFiniteNumber(quality.score);
        const level = quality.level || "not_available";

        const normalizedScore = score === null
            ? 0
            : clamp(score, 0, 100);

        const scoreText = score === null
            ? "—"
            : `${Math.round(normalizedScore)}%`;

        element.innerHTML = `
            <section class="telemetry-intelligence-card">
                <div class="telemetry-card-heading">
                    <div>
                        <small>
                            ${escapeHtml(translate(
                                "Ocena wiarygodności telemetrycznej",
                                "Telemetry reliability assessment",
                            ))}
                        </small>

                        <h4>
                            ${escapeHtml(translate(
                                "Jakość danych",
                                "Data quality",
                            ))}
                        </h4>
                    </div>

                    <span class="${escapeHtml(
                        qualityBadgeClass(level),
                    )}">
                        ${escapeHtml(scoreText)}
                    </span>
                </div>

                <div
                    class="telemetry-quality-meter"
                    role="progressbar"
                    aria-valuemin="0"
                    aria-valuemax="100"
                    aria-valuenow="${escapeHtml(
                        String(normalizedScore),
                    )}"
                    aria-label="${escapeHtml(translate(
                        "Ocena jakości danych",
                        "Data quality score",
                    ))}"
                >
                    <span
                        style="width: ${escapeHtml(
                            String(normalizedScore),
                        )}%"
                    ></span>
                </div>

                <div class="telemetry-metric-grid">
                    ${renderQualityMetric(
                        translate("Poziom", "Level"),
                        translateDictionaryValue(
                            QUALITY_LABELS,
                            level,
                        ),
                    )}

                    ${renderQualityMetric(
                        translate(
                            "Kompletność czasu",
                            "Timestamp completeness",
                        ),
                        formatPercent(
                            quality.timestamp_completeness_percent,
                        ),
                    )}

                    ${renderQualityMetric(
                        translate(
                            "Prawidłowe RR",
                            "Valid RR intervals",
                        ),
                        formatInteger(
                            quality.rr_valid_count,
                        ),
                    )}

                    ${renderQualityMetric(
                        translate(
                            "Odrzucone RR",
                            "Rejected RR intervals",
                        ),
                        formatInteger(
                            quality.rr_invalid_count,
                        ),
                    )}

                    ${renderQualityMetric(
                        translate(
                            "Luki czasowe",
                            "Time gaps",
                        ),
                        formatInteger(
                            quality.gaps_detected,
                        ),
                    )}

                    ${renderQualityMetric(
                        translate(
                            "Największa luka",
                            "Largest gap",
                        ),
                        formatSeconds(
                            quality.largest_gap_seconds,
                        ),
                    )}
                </div>
            </section>
        `;
    }

    /**
     * Renderuje dostępne funkcje analityczne.
     */
    function renderAnalysisAvailability(
        input,
        target = DEFAULT_TARGETS.analysis,
    ) {
        const report = normalizeReport(input);
        const element = resolveElement(target);

        if (!element) {
            return;
        }

        const analysis = asObject(report.analysis);
        const available = asObject(analysis.available);
        const entries = Object.entries(available);

        const enabledCount = entries.filter(
            ([, enabled]) => Boolean(enabled),
        ).length;

        const analysisLevel = normalizeAnalysisLevel(
            analysis.analysis_level,
        );

        const confidence = translateDictionaryValue(
            CONFIDENCE_LABELS,
            analysis.confidence || "not_available",
        );

        element.innerHTML = `
            <section class="telemetry-intelligence-card">
                <div class="telemetry-card-heading">
                    <div>
                        <small>
                            ${escapeHtml(translate(
                                "Zakres określony na podstawie rzeczywistych danych",
                                "Scope determined from actual telemetry",
                            ))}
                        </small>

                        <h4>
                            ${escapeHtml(translate(
                                "Dostępne analizy",
                                "Available analyses",
                            ))}
                        </h4>
                    </div>

                    <span
                        class="telemetry-status-badge telemetry-status-ready"
                        title="${escapeHtml(translate(
                            "Liczba dostępnych analiz",
                            "Number of available analyses",
                        ))}"
                    >
                        ${enabledCount}/${entries.length}
                    </span>
                </div>

                <div class="telemetry-analysis-level">
                    <div>
                        <small>
                            ${escapeHtml(translate(
                                "Poziom analizy",
                                "Analysis level",
                            ))}
                        </small>

                        <strong>
                            ${escapeHtml(String(analysisLevel))}/5
                        </strong>
                    </div>

                    <div>
                        <small>
                            ${escapeHtml(translate(
                                "Pewność analizy",
                                "Analysis confidence",
                            ))}
                        </small>

                        <strong>
                            ${escapeHtml(confidence)}
                        </strong>
                    </div>
                </div>

                ${
                    entries.length
                        ? `
                            <div class="telemetry-capability-grid">
                                ${entries.map(
                                    ([key, enabled]) => (
                                        renderCapabilityItem(
                                            translateDictionaryValue(
                                                ANALYSIS_LABELS,
                                                key,
                                            ),
                                            Boolean(enabled),
                                        )
                                    ),
                                ).join("")}
                            </div>
                        `
                        : renderInlineEmptyState(
                            translate(
                                "Zakres analiz nie został jeszcze określony.",
                                "Analysis availability has not been determined yet.",
                            ),
                        )
                }

                ${renderLimitations(
                    analysis.limitations,
                )}
            </section>
        `;
    }

    /**
     * Renderuje zalecany następny krok.
     */
    function renderTelemetryRecommendation(
        input,
        target = DEFAULT_TARGETS.recommendation,
    ) {
        const report = normalizeReport(input);
        const element = resolveElement(target);

        if (!element) {
            return;
        }

        const analysis = asObject(report.analysis);

        const recommendation = localizeBackendMessage(
            analysis.next_recommended_action,
        ) || translate(
            "Wgraj plik telemetryczny, aby system wykrył dostępne sygnały.",
            "Upload a telemetry file to detect available signals.",
        );

        element.innerHTML = `
            <section class="telemetry-recommendation-card">
                <small>
                    ${escapeHtml(translate(
                        "Rekomendowany następny krok",
                        "Recommended next step",
                    ))}
                </small>

                <strong>
                    ${escapeHtml(recommendation)}
                </strong>
            </section>
        `;
    }

    /**
     * Czyści wszystkie sekcje Telemetry Intelligence.
     */
    function clearTelemetryIntelligence(options = {}) {
        const targets = resolveTargets(options);

        Object.values(targets).forEach((target) => {
            const element = resolveElement(target);

            if (element) {
                element.replaceChildren();
            }
        });
    }

    /**
     * Wyświetla stan oczekiwania przed wgraniem danych.
     */
    function renderPending(options = {}) {
        const targets = resolveTargets(options);

        renderPendingCard(
            targets.capabilities,
            translate(
                "Oczekiwanie na dane telemetryczne",
                "Waiting for telemetry data",
            ),
            translate(
                "Wgraj plik HR/RR, SpO₂ lub inne dane z timestampami.",
                "Upload HR/RR, SpO₂ or other timestamped telemetry.",
            ),
        );

        clearElement(targets.quality);
        clearElement(targets.analysis);
        clearElement(targets.recommendation);
    }

    /**
     * Wyświetla stan skanowania pliku.
     */
    function renderScanning(options = {}) {
        const targets = resolveTargets(options);

        renderPendingCard(
            targets.capabilities,
            translate(
                "Analizowanie pliku",
                "Analyzing file",
            ),
            translate(
                "System rozpoznaje sygnały, zakres czasu i jakość danych.",
                "Detecting signals, time coverage and data quality.",
            ),
            true,
        );

        clearElement(targets.quality);
        clearElement(targets.analysis);
        clearElement(targets.recommendation);
    }

    /**
     * Wyświetla błąd skanowania lub raportowania.
     */
    function renderError(message, options = {}) {
        const targets = resolveTargets(options);
        const element = resolveElement(targets.capabilities);

        if (!element) {
            return;
        }

        element.innerHTML = `
            <section class="telemetry-intelligence-card telemetry-error-card">
                <div class="telemetry-card-heading">
                    <div>
                        <small>
                            ${escapeHtml(translate(
                                "Telemetry Intelligence",
                                "Telemetry Intelligence",
                            ))}
                        </small>

                        <h4>
                            ${escapeHtml(translate(
                                "Nie udało się przeanalizować danych",
                                "Telemetry analysis failed",
                            ))}
                        </h4>
                    </div>

                    <span
                        class="telemetry-status-badge telemetry-status-unavailable"
                    >
                        !
                    </span>
                </div>

                <p>
                    ${escapeHtml(
                        message || translate(
                            "Wystąpił nieoczekiwany błąd.",
                            "An unexpected error occurred.",
                        ),
                    )}
                </p>
            </section>
        `;

        clearElement(targets.quality);
        clearElement(targets.analysis);
        clearElement(targets.recommendation);
    }

    function renderPendingCard(
        target,
        title,
        description,
        loading = false,
    ) {
        const element = resolveElement(target);

        if (!element) {
            return;
        }

        element.innerHTML = `
            <section class="telemetry-intelligence-card telemetry-pending-card">
                <div class="telemetry-card-heading">
                    <div>
                        <small>Telemetry Intelligence</small>
                        <h4>${escapeHtml(title)}</h4>
                    </div>

                    ${
                        loading
                            ? `
                                <span
                                    class="telemetry-loading-indicator"
                                    aria-label="${escapeHtml(translate(
                                        "Analizowanie",
                                        "Analyzing",
                                    ))}"
                                ></span>
                            `
                            : ""
                    }
                </div>

                <p>${escapeHtml(description)}</p>
            </section>
        `;
    }

    function renderCapabilityItem(label, available) {
        const statusClass = available
            ? "telemetry-capability-available"
            : "telemetry-capability-unavailable";

        const icon = available ? "✓" : "—";

        const statusText = available
            ? translate("Dostępne", "Available")
            : translate("Niedostępne", "Unavailable");

        return `
            <div class="telemetry-capability-item ${statusClass}">
                <span
                    class="telemetry-capability-icon"
                    aria-hidden="true"
                >
                    ${icon}
                </span>

                <div>
                    <strong>${escapeHtml(label)}</strong>
                    <small>${escapeHtml(statusText)}</small>
                </div>
            </div>
        `;
    }

    function renderSummaryMetric(label, value) {
        return `
            <div class="telemetry-summary-metric">
                <small>${escapeHtml(label)}</small>
                <strong>${escapeHtml(String(value ?? "—"))}</strong>
            </div>
        `;
    }

    function renderQualityMetric(label, value) {
        return `
            <div class="telemetry-quality-metric">
                <small>${escapeHtml(label)}</small>
                <strong>${escapeHtml(String(value ?? "—"))}</strong>
            </div>
        `;
    }

    function renderLimitations(limitations) {
        if (
            !Array.isArray(limitations)
            || limitations.length === 0
        ) {
            return "";
        }

        return `
            <details class="telemetry-limitations">
                <summary>
                    ${escapeHtml(translate(
                        "Ograniczenia analizy",
                        "Analysis limitations",
                    ))}
                </summary>

                <ul>
                    ${limitations
                        .filter((item) => item !== null && item !== undefined)
                        .map((item) => `
                            <li>
                                ${escapeHtml(
                                    localizeBackendMessage(String(item)),
                                )}
                            </li>
                        `)
                        .join("")}
                </ul>
            </details>
        `;
    }

    function renderInlineEmptyState(message) {
        return `
            <div class="telemetry-inline-empty">
                ${escapeHtml(message)}
            </div>
        `;
    }

    function renderEmptyState(targets) {
        renderPending({
            capabilitiesTarget: targets.capabilities,
            qualityTarget: targets.quality,
            analysisTarget: targets.analysis,
            recommendationTarget: targets.recommendation,
        });
    }

    function normalizeReport(input) {
        if (!input || typeof input !== "object") {
            return {};
        }

        if (
            input.telemetry_intelligence
            && typeof input.telemetry_intelligence === "object"
        ) {
            return input.telemetry_intelligence;
        }

        return input;
    }

    function hasReportData(report) {
        if (!report || typeof report !== "object") {
            return false;
        }

        return Boolean(
            Object.keys(asObject(report.file)).length
            || Object.keys(asObject(report.signals)).length
            || Object.keys(asObject(report.quality)).length
            || Object.keys(asObject(report.analysis)).length
        );
    }

    function resolveTargets(options = {}) {
        return {
            capabilities:
                options.capabilitiesTarget
                || options.capabilities
                || DEFAULT_TARGETS.capabilities,

            quality:
                options.qualityTarget
                || options.quality
                || DEFAULT_TARGETS.quality,

            analysis:
                options.analysisTarget
                || options.analysis
                || DEFAULT_TARGETS.analysis,

            recommendation:
                options.recommendationTarget
                || options.recommendation
                || DEFAULT_TARGETS.recommendation,
        };
    }

    function resolveElement(target) {
        if (
            typeof HTMLElement !== "undefined"
            && target instanceof HTMLElement
        ) {
            return target;
        }

        if (typeof target !== "string" || !target.trim()) {
            return null;
        }

        return document.getElementById(target);
    }

    function clearElement(target) {
        const element = resolveElement(target);

        if (element) {
            element.replaceChildren();
        }
    }

    function getLanguage() {
        const htmlLanguage = String(
            document.documentElement.lang || "pl",
        ).toLowerCase();

        return htmlLanguage.startsWith("en")
            ? "en"
            : "pl";
    }

    function translate(polishText, englishText) {
        return getLanguage() === "en"
            ? englishText
            : polishText;
    }

    function translateDictionaryValue(
        dictionary,
        key,
    ) {
        const entry = dictionary[key];

        if (!entry) {
            return humanizeKey(key);
        }

        const language = getLanguage();

        return entry[language]
            || entry.en
            || entry.pl
            || humanizeKey(key);
    }

    /**
     * Backend może zwracać angielskie komunikaty.
     * Dla najczęstszych zaleceń podmieniamy je na wersję polską.
     */
    function localizeBackendMessage(message) {
        if (!message) {
            return "";
        }

        if (getLanguage() === "en") {
            return String(message);
        }

        const translations = {
            "Telemetry is ready for analysis.":
                "Dane telemetryczne są gotowe do analizy.",

            "Upload telemetry containing timestamps.":
                "Wgraj dane telemetryczne zawierające znaczniki czasu.",

            "Upload a heart-rate telemetry file to enable cardiovascular trend analysis.":
                "Wgraj dane tętna, aby włączyć analizę trendu sercowo-naczyniowego.",

            "Upload telemetry containing valid RR intervals or timestamped HRV measurements.":
                "Wgraj dane zawierające prawidłowe interwały RR lub pomiary HRV ze znacznikami czasu.",

            "Upload timestamped SpO₂ and pulse data to enable oxygenation analysis.":
                "Wgraj dane SpO₂ i pulsu ze znacznikami czasu, aby włączyć analizę natlenienia.",

            "Review timestamp continuity and signal artifacts before interpreting trends.":
                "Przed interpretacją trendów sprawdź ciągłość czasu i artefakty sygnału.",

            "The current telemetry supports HRV analysis and can be merged with timestamped pulse-oximetry data.":
                "Bieżące dane obsługują analizę HRV i mogą zostać połączone z danymi pulsoksymetrycznymi ze znacznikami czasu.",

            "The current telemetry supports oxygen analysis and can be merged with timestamped HR/RR telemetry.":
                "Bieżące dane obsługują analizę natlenienia i mogą zostać połączone z danymi HR/RR ze znacznikami czasu.",

            "Full physiological session analysis is available.":
                "Dostępna jest pełna analiza fizjologiczna sesji.",

            "Timestamp data is unavailable; time synchronization cannot be performed.":
                "Brak znaczników czasu; synchronizacja danych nie jest możliwa.",

            "Heart-rate telemetry is unavailable.":
                "Dane tętna są niedostępne.",

            "RR intervals and reported HRV are unavailable; HRV analysis is disabled.":
                "Brak interwałów RR i raportowanego HRV; analiza HRV jest wyłączona.",

            "Too few valid RR intervals are available for reliable HRV calculation.":
                "Liczba prawidłowych interwałów RR jest zbyt mała do wiarygodnego obliczenia HRV.",

            "SpO₂ telemetry is unavailable; oxygenation analysis is disabled.":
                "Brak danych SpO₂; analiza natlenienia jest wyłączona.",

            "Telemetry quality is too low for reliable physiological interpretation.":
                "Jakość danych jest zbyt niska do wiarygodnej interpretacji fizjologicznej.",

            "The current source cannot be synchronized reliably with another timeline.":
                "Bieżącego źródła nie można wiarygodnie zsynchronizować z inną osią czasu.",
        };

        return translations[String(message)]
            || String(message);
    }

    function qualityBadgeClass(level) {
        if (level === "excellent" || level === "good") {
            return [
                "telemetry-status-badge",
                "telemetry-status-ready",
            ].join(" ");
        }

        if (level === "fair") {
            return [
                "telemetry-status-badge",
                "telemetry-status-warning",
            ].join(" ");
        }

        return [
            "telemetry-status-badge",
            "telemetry-status-unavailable",
        ].join(" ");
    }

    function normalizeAnalysisLevel(value) {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return 1;
        }

        return Math.round(
            clamp(number, 1, 5),
        );
    }

    function formatDuration(value) {
        const seconds = toFiniteNumber(value);

        if (seconds === null || seconds <= 0) {
            return "—";
        }

        const totalMinutes = Math.round(seconds / 60);
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;

        if (hours > 0) {
            return `${hours} h ${minutes} min`;
        }

        return `${minutes} min`;
    }

    function formatPercent(value) {
        const number = toFiniteNumber(value);

        if (number === null) {
            return "—";
        }

        return `${number.toFixed(1)}%`;
    }

    function formatInteger(value) {
        const number = toFiniteNumber(value);

        if (number === null) {
            return "—";
        }

        return Math.round(number).toLocaleString(
            getLanguage() === "en"
                ? "en-US"
                : "pl-PL",
        );
    }

    function formatSeconds(value) {
        const number = toFiniteNumber(value);

        if (number === null || number <= 0) {
            return "0 s";
        }

        const precision = number < 10 ? 1 : 0;

        return `${number.toFixed(precision)} s`;
    }

    function toFiniteNumber(value) {
        if (
            value === null
            || value === undefined
            || value === ""
            || typeof value === "boolean"
        ) {
            return null;
        }

        const number = Number(value);

        return Number.isFinite(number)
            ? number
            : null;
    }

    function clamp(value, minimum, maximum) {
        return Math.min(
            Math.max(value, minimum),
            maximum,
        );
    }

    function asObject(value) {
        if (
            value
            && typeof value === "object"
            && !Array.isArray(value)
        ) {
            return value;
        }

        return {};
    }

    function humanizeKey(value) {
        return String(value || "")
            .replaceAll("_", " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    global.TelemetryIntelligence = Object.freeze({
        render: renderTelemetryIntelligence,
        renderCapabilities: renderTelemetryCapabilities,
        renderQuality: renderTelemetryQuality,
        renderAnalysis: renderAnalysisAvailability,
        renderRecommendation: renderTelemetryRecommendation,
        renderPending,
        renderScanning,
        renderError,
        clear: clearTelemetryIntelligence,
    });

    document.addEventListener("DOMContentLoaded", () => {
        const capabilitiesElement = document.getElementById(
            DEFAULT_TARGETS.capabilities,
        );

        if (
            capabilitiesElement
            && !capabilitiesElement.hasChildNodes()
        ) {
            renderPending();
        }
    });
})(window);