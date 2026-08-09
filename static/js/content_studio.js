"use strict";


const ContentStudio = (() => {
    const API_URL = "/content-studio/api/media";

    const state = {
        media: [],
        filters: {
            type: "",
            scene: "",
            character: "",
            status: "",
            isFinal: "",
        },
    };


    function getCsrfToken() {
        const meta = document.querySelector(
            'meta[name="csrf-token"]'
        );

        if (meta?.content) {
            return meta.content;
        }

        const input = document.querySelector(
            'input[name="csrf_token"]'
        );

        return input?.value || "";
    }


    function buildHeaders() {
        const headers = {
            "Content-Type": "application/json",
        };

        const csrfToken = getCsrfToken();

        if (csrfToken) {
            headers["X-CSRFToken"] = csrfToken;
        }

        return headers;
    }


    async function parseResponse(response) {
        let result;

        try {
            result = await response.json();
        } catch {
            throw new Error(
                `Unexpected server response (${response.status})`
            );
        }

        if (!response.ok) {
            throw new Error(
                result.error
                || `Request failed (${response.status})`
            );
        }

        return result;
    }


    async function registerMedia(mediaData) {
        const response = await fetch(API_URL, {
            method: "POST",
            credentials: "same-origin",
            headers: buildHeaders(),
            body: JSON.stringify(mediaData),
        });

        const result = await parseResponse(response);
        return result.media;
    }


    async function fetchMedia(filters = {}) {
        const params = new URLSearchParams();

        if (filters.type) {
            params.set("type", filters.type);
        }

        if (filters.scene) {
            params.set("scene", filters.scene);
        }

        if (filters.character) {
            params.set(
                "character",
                filters.character
            );
        }

        if (filters.status) {
            params.set("status", filters.status);
        }

        if (filters.isFinal !== "") {
            params.set(
                "is_final",
                String(filters.isFinal)
            );
        }

        params.set("limit", "200");

        const query = params.toString();
        const url = query
            ? `${API_URL}?${query}`
            : API_URL;

        const response = await fetch(url, {
            method: "GET",
            credentials: "same-origin",
            headers: {
                "Accept": "application/json",
            },
        });

        const result = await parseResponse(response);
        return result.media;
    }


    async function updateMedia(
        mediaId,
        updateData
    ) {
        const response = await fetch(
            `${API_URL}/${mediaId}`,
            {
                method: "PATCH",
                credentials: "same-origin",
                headers: buildHeaders(),
                body: JSON.stringify(updateData),
            }
        );

        const result = await parseResponse(response);
        return result.media;
    }


    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }


    function formatBytes(value) {
        const bytes = Number(value);

        if (!Number.isFinite(bytes) || bytes <= 0) {
            return "—";
        }

        const units = [
            "B",
            "KB",
            "MB",
            "GB",
        ];

        const unitIndex = Math.min(
            Math.floor(Math.log(bytes) / Math.log(1024)),
            units.length - 1
        );

        const amount = bytes / (1024 ** unitIndex);

        return `${amount.toFixed(
            unitIndex === 0 ? 0 : 1
        )} ${units[unitIndex]}`;
    }


    function formatDate(value) {
        if (!value) {
            return "—";
        }

        const date = new Date(value);

        if (Number.isNaN(date.getTime())) {
            return escapeHtml(value);
        }

        return new Intl.DateTimeFormat("pl-PL", {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(date);
    }


    function buildPreview(item) {
        const fileUrl =
            `${API_URL}/${item.id}/file`;

        if (
            item.media_type === "image"
            || item.media_type === "thumbnail"
            || item.media_type === "social"
        ) {
            return `
                <img
                    class="content-media-preview"
                    src="${fileUrl}"
                    alt="${escapeHtml(item.file_name)}"
                    loading="lazy"
                    data-preview-media-id="${item.id}"
                >
            `;
        }

        if (item.media_type === "video") {
            return `
                <video
                    class="content-media-preview"
                    controls
                    preload="metadata"
                    data-preview-media-id="${item.id}"
                >
                    <source
                        src="${fileUrl}"
                        type="${escapeHtml(
                            item.mime_type || "video/mp4"
                        )}"
                    >
                </video>
            `;
        }

        return `
            <div class="content-media-placeholder">
                No preview
            </div>
        `;
    }


    function buildMediaCard(item) {
        const finalBadge = item.is_final
            ? '<span class="media-badge final">FINAL</span>'
            : "";
        const mediaType = escapeHtml(item.media_type || "media");
        const status = escapeHtml(item.status || "unknown");

        return `
            <article
                class="content-media-card"
                data-media-id="${item.id}"
            >
                <div class="content-media-preview-wrap">
                    ${buildPreview(item)}
                    <span class="media-badge media-type-badge">${mediaType}</span>
                    <span class="media-badge media-status-badge">${status}</span>
                </div>

                <div class="content-media-body">
                    <div class="content-media-title-row">
                        <h3>
                            ${escapeHtml(item.file_name)}
                        </h3>

                        ${finalBadge}
                    </div>

                    <dl class="content-media-meta">
                        <div>
                            <dt>Scene</dt>
                            <dd>${escapeHtml(item.scene_id)}</dd>
                        </div>

                        <div>
                            <dt>Character</dt>
                            <dd>${escapeHtml(item.character_id)}</dd>
                        </div>

                        <div>
                            <dt>Provider</dt>
                            <dd>${escapeHtml(item.ai_provider)}</dd>
                        </div>

                        <div>
                            <dt>Version</dt>
                            <dd>${escapeHtml(item.version)}</dd>
                        </div>

                        <div>
                            <dt>Size</dt>
                            <dd>
                                ${formatBytes(item.file_size_bytes)}
                            </dd>
                        </div>

                        <div>
                            <dt>Created</dt>
                            <dd>${formatDate(item.created_at)}</dd>
                        </div>
                    </dl>

                    <details class="content-media-details">
                        <summary>Prompt and path</summary>

                        <p class="content-media-prompt">
                            ${escapeHtml(item.prompt)}
                        </p>

                        <code>
                            ${escapeHtml(item.file_path)}
                        </code>
                    </details>

                    <div class="content-media-actions">
                        <a
                            class="studio-button outline"
                            href="${fileUrlFor(item.id)}"
                            target="_blank"
                            rel="noopener"
                        >
                            Open
                        </a>

                        <a
                            class="studio-button outline"
                            href="${fileUrlFor(item.id)}"
                            download="${escapeHtml(item.file_name)}"
                        >
                            Download
                        </a>

                        <select
                            class="media-status-select"
                            aria-label="Media status"
                        >
                            ${buildStatusOptions(item.status)}
                        </select>

                        <label class="media-final-label">
                            <input
                                type="checkbox"
                                class="media-final-checkbox"
                                ${item.is_final ? "checked" : ""}
                            >
                            Final
                        </label>

                        <button
                            type="button"
                            class="media-save-button"
                        >
                            Save
                        </button>
                    </div>
                </div>
            </article>
        `;
    }

    function showPreviewUnavailable(element) {
        const wrapper = element.closest(".content-media-preview-wrap");
        if (!wrapper || wrapper.querySelector(".content-media-preview-unavailable")) {
            return;
        }

        element.remove();
        const fallback = document.createElement("div");
        fallback.className = "content-media-preview-unavailable";
        fallback.setAttribute("role", "status");
        fallback.textContent = "Preview unavailable";
        wrapper.prepend(fallback);
    }

    function fileUrlFor(mediaId) {
        return `${API_URL}/${mediaId}/file`;
    }


    function buildStatusOptions(selectedStatus) {
        const statuses = [
            "draft",
            "generated",
            "approved",
            "published",
            "archived",
            "failed",
        ];

        return statuses
            .map((status) => `
                <option
                    value="${status}"
                    ${status === selectedStatus
                        ? "selected"
                        : ""}
                >
                    ${status}
                </option>
            `)
            .join("");
    }


    async function renderMediaList() {
        const container = document.getElementById(
            "media-list"
        );

        if (!container) {
            return;
        }

        container.innerHTML = `
            <p class="content-studio-message">
                Loading media...
            </p>
        `;
        container.setAttribute("aria-busy", "true");

        try {
            state.media = await fetchMedia(
                state.filters
            );

            if (!state.media.length) {
                container.innerHTML = `
                    <p class="content-studio-message">
                        No generated media found.
                    </p>
                `;
                return;
            }

            container.innerHTML = state.media
                .map(buildMediaCard)
                .join("");

        } catch (error) {
            container.innerHTML = `
                <p class="content-studio-error">
                    ${escapeHtml(error.message)}
                </p>
            `;
        } finally {
            container.setAttribute("aria-busy", "false");
        }
    }


    function readFormData(form) {
        const formData = new FormData(form);

        const optionalNumber = (name) => {
            const value = formData.get(name);

            return value
                ? Number(value)
                : null;
        };

        return {
            media_type: formData.get("media_type"),
            scene_id: formData.get("scene_id"),
            character_id: formData.get(
                "character_id"
            ),
            version: formData.get("version"),
            ai_provider: formData.get(
                "ai_provider"
            ),
            prompt: formData.get("prompt"),
            negative_prompt: formData.get(
                "negative_prompt"
            ) || null,
            file_path: formData.get("file_path"),
            mime_type:
                formData.get("mime_type") || null,
            width: optionalNumber("width"),
            height: optionalNumber("height"),
            duration_seconds:
                optionalNumber("duration_seconds"),
            status: formData.get("status"),
            is_final: formData.get("is_final") === "on",
            notes: formData.get("notes") || null,
        };
    }


    async function handleFormSubmit(event) {
        event.preventDefault();

        const form = event.currentTarget;
        const message = document.getElementById(
            "media-form-message"
        );
        const submitButton = form.querySelector(
            'button[type="submit"]'
        );

        submitButton.disabled = true;

        if (message) {
            message.textContent = "Saving...";
            message.className =
                "content-studio-message";
        }

        try {
            const mediaData = readFormData(form);

            await registerMedia(mediaData);

            form.reset();

            if (message) {
                message.textContent =
                    "Media record saved.";
                message.className =
                    "content-studio-success";
            }

            await renderMediaList();

        } catch (error) {
            if (message) {
                message.textContent = error.message;
                message.className =
                    "content-studio-error";
            }

        } finally {
            submitButton.disabled = false;
        }
    }


    function readFilters() {
        state.filters = {
            type:
                document.getElementById(
                    "filter-type"
                )?.value || "",
            scene:
                document.getElementById(
                    "filter-scene"
                )?.value.trim() || "",
            character:
                document.getElementById(
                    "filter-character"
                )?.value.trim() || "",
            status:
                document.getElementById(
                    "filter-status"
                )?.value || "",
            isFinal:
                document.getElementById(
                    "filter-final"
                )?.value || "",
        };
    }


    async function handleFilterSubmit(event) {
        event.preventDefault();
        readFilters();
        await renderMediaList();
    }


    async function handleMediaAction(event) {
        const button = event.target.closest(
            ".media-save-button"
        );

        if (!button) {
            return;
        }

        const card = button.closest(
            ".content-media-card"
        );

        if (!card) {
            return;
        }

        const mediaId = Number(card.dataset.mediaId);
        const status = card.querySelector(
            ".media-status-select"
        )?.value;
        const isFinal = card.querySelector(
            ".media-final-checkbox"
        )?.checked || false;

        button.disabled = true;
        button.textContent = "Saving...";

        try {
            await updateMedia(mediaId, {
                status,
                is_final: isFinal,
            });

            button.textContent = "Saved";

            setTimeout(() => {
                button.textContent = "Save";
            }, 1200);

            await renderMediaList();

        } catch (error) {
            button.textContent = "Error";
            window.alert(error.message);

        } finally {
            button.disabled = false;
        }
    }


    function init() {
        const form = document.getElementById(
            "media-form"
        );
        const filterForm = document.getElementById(
            "media-filter-form"
        );
        const mediaList = document.getElementById(
            "media-list"
        );

        form?.addEventListener(
            "submit",
            handleFormSubmit
        );

        filterForm?.addEventListener(
            "submit",
            handleFilterSubmit
        );

        mediaList?.addEventListener(
            "click",
            handleMediaAction
        );

        mediaList?.addEventListener("error", (event) => {
            const preview = event.target.closest(".content-media-preview");
            if (preview) {
                showPreviewUnavailable(preview);
            }
        }, true);

        renderMediaList();
    }


    return {
        init,
        registerMedia,
        fetchMedia,
        updateMedia,
    };
})();


document.addEventListener(
    "DOMContentLoaded",
    ContentStudio.init
);
