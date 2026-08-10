document.addEventListener("DOMContentLoaded", function () {

    const form =
        document.getElementById("generation-form");

    const provider =
        document.getElementById("provider");

    const outputType =
        document.getElementById("output-type");

    const character =
        document.getElementById("character");

    const scene =
        document.getElementById("scene");

    const storyboard =
        document.getElementById("storyboard");

    const promptPreview =
        document.getElementById("prompt-preview");

    const generateButton =
        document.getElementById("generate-button");

    const progress =
        document.getElementById("generation-progress");

    const progressBar =
        document.getElementById("generation-progress-bar");

    const status =
        document.getElementById("generation-status");

    const percent =
        document.getElementById("generation-percent");

    const message =
        document.getElementById("generation-message");

    const mediaLink =
        document.getElementById("generation-media-link");

    let providerCapabilities = {};


    if (
        !form ||
        !provider ||
        !outputType ||
        !character ||
        !scene ||
        !promptPreview ||
        !generateButton
    ) {
        console.error(
            "AI Content Studio: generation form elements are missing."
        );

        return;
    }


    // ======================================================
    // PROMPT BUILDER
    // ======================================================

    function buildPrompt() {

        const lines = [
            "CoreLabTech AI Content Studio",
            "",
            "Character: " + character.value,
            "Scene: " + scene.value,
            "Output: " + outputType.value
        ];


        if (
            storyboard &&
            storyboard.value
        ) {
            lines.push(
                "Storyboard: " + storyboard.value
            );
        }


        lines.push(
            "",
            "Use the official CoreLabTech character reference.",
            "",
            "Preserve exactly:",
            "- character identity",
            "- facial features",
            "- hairstyle",
            "- body proportions",
            "- clothing",
            "- HR chest strap",
            "- smartwatch",
            "",
            "Visual style:",
            "- premium CoreLabTech commercial style",
            "- dark navy environment",
            "- electric blue accents",
            "- cyan highlights",
            "- professional cinematic lighting",
            "- modern technology aesthetic",
            "- realistic human proportions",
            "",
            "Do not include:",
            "- commercial logos",
            "- watermark",
            "- distorted anatomy",
            "- duplicated limbs",
            "- extra fingers",
            "- incorrect face",
            "- different hairstyle"
        );


        return lines.join("\n");
    }


    function refreshPrompt() {

        promptPreview.value =
            buildPrompt();
    }


    function applyProviderCapabilities() {
        const supported = providerCapabilities[provider.value]
            ?.supported_output_types || [];

        Array.from(outputType.options).forEach((option) => {
            const supportedByProvider = supported.includes(option.value);
            option.disabled = !supportedByProvider;
            option.textContent = supportedByProvider
                ? option.value.charAt(0).toUpperCase() + option.value.slice(1)
                : option.value.charAt(0).toUpperCase() + option.value.slice(1)
                    + " — unavailable for this provider";
        });

        if (!supported.includes(outputType.value)) {
            outputType.value = supported[0] || "";
        }
        refreshPrompt();
    }

    async function loadProviderCapabilities() {
        generateButton.disabled = true;
        setMessage("Loading provider capabilities...", null);

        try {
            const response = await fetch(
                "/content-studio/api/provider-capabilities",
                { credentials: "same-origin", headers: { "Accept": "application/json" } }
            );
            const data = await parseResponse(response);
            providerCapabilities = data.providers || {};

            Array.from(provider.options).forEach((option) => {
                const capability = providerCapabilities[option.value];
                option.disabled = !capability;
                option.textContent = capability
                    ? (capability.label || option.value)
                    : `${option.value} — not connected`;
            });

            if (!providerCapabilities[provider.value]) {
                provider.value = Object.keys(providerCapabilities)[0] || "";
            }

            applyProviderCapabilities();
            generateButton.disabled = !provider.value || !outputType.value;
            setMessage("", null);
        } catch (error) {
            providerCapabilities = {};
            applyProviderCapabilities();
            generateButton.disabled = true;
            setProgress(0, "Unavailable");
            setMessage("Provider capabilities are unavailable. Generation is disabled until they can be loaded.", "error");
        }
    }

    provider.addEventListener("change", applyProviderCapabilities);

    outputType.addEventListener(
        "change",
        refreshPrompt
    );

    character.addEventListener(
        "change",
        refreshPrompt
    );

    scene.addEventListener(
        "change",
        refreshPrompt
    );


    if (storyboard) {
        storyboard.addEventListener(
            "change",
            refreshPrompt
        );
    }

    loadProviderCapabilities();


    // ======================================================
    // UI HELPERS
    // ======================================================

    function setProgress(
        value,
        statusText
    ) {

        if (!progress) {
            return;
        }


        progress.classList.add(
            "is-visible"
        );


        if (progressBar) {
            progressBar.style.width =
                value + "%";
        }


        if (percent) {
            percent.textContent =
                value + "%";
        }


        if (status && statusText) {
            status.textContent =
                statusText;
        }
    }


    function setMessage(
        text,
        type
    ) {

        if (!message) {
            return;
        }


        message.textContent =
            text || "";


        message.classList.remove(
            "success",
            "error"
        );


        if (type) {
            message.classList.add(
                type
            );
        }
    }


    function setButtonLoading(
        loading
    ) {

        generateButton.disabled =
            loading;


        generateButton.textContent =
            loading
                ? "Generating..."
                : "Generate";
    }


    // ======================================================
    // CSRF
    // ======================================================

    function getCsrfToken() {

        const element =
            document.querySelector(
                'meta[name="csrf-token"]'
            );


        if (!element) {
            return null;
        }


        return element.getAttribute(
            "content"
        );
    }


    // ======================================================
    // RESPONSE HANDLING
    // ======================================================

    async function parseResponse(
        response
    ) {

        const contentType =
            response.headers.get(
                "content-type"
            ) || "";


        if (
            contentType.includes(
                "application/json"
            )
        ) {

            return await response.json();
        }


        const text =
            await response.text();


        console.error(
            "AI Content Studio received non-JSON response:",
            {
                status:
                    response.status,

                statusText:
                    response.statusText,

                response:
                    text
            }
        );


        throw new Error(
            "The generation service returned an unexpected response (HTTP " +
            response.status + ")."
        );
    }


    // ======================================================
    // GENERATE
    // ======================================================

    form.addEventListener(
        "submit",
        async function (event) {

            event.preventDefault();


            setMessage("", null);

            setButtonLoading(true);

            setProgress(
                10,
                "Creating generation job..."
            );


            const csrfToken =
                getCsrfToken();


            if (!csrfToken) {

                setProgress(
                    0,
                    "Failed"
                );


                setMessage(
                    "The security token is unavailable. Refresh the page and try again.",
                    "error"
                );


                setButtonLoading(false);

                return;
            }


            const payload = {

                provider:
                    provider.value,

                output_type:
                    outputType.value,

                character_id:
                    character.value,

                scene_id:
                    scene.value,

                storyboard_id:
                    storyboard
                        ? storyboard.value || null
                        : null,

                prompt:
                    promptPreview.value
            };


            console.log(
                "Starting generation job:",
                payload
            );


            try {

                setProgress(
                    25,
                    "Sending request..."
                );


                const response =
                    await fetch(
                        "/content-studio/api/generation-jobs",
                        {
                            method:
                                "POST",

                            credentials:
                                "same-origin",

                            headers: {
                                "Content-Type":
                                    "application/json",

                                "Accept":
                                    "application/json",

                                "X-CSRFToken":
                                    csrfToken
                            },

                            body:
                                JSON.stringify(
                                    payload
                                )
                        }
                    );


                setProgress(
                    55,
                    "Processing response..."
                );


                const data =
                    await parseResponse(
                        response
                    );


                if (!response.ok) {

                    throw new Error(
                        data.error ||
                        (
                            "Generation request failed with HTTP " +
                            response.status
                        )
                    );
                }


                if (
                    !data ||
                    data.status !== "success" ||
                    !data.job
                ) {

                    throw new Error(
                        "Invalid generation API response."
                    );
                }


                setProgress(
                    data.job.progress_percent ?? 100,
                    data.job.status || "Completed"
                );


                setMessage(
                    "Mock Provider created and registered a deterministic development artifact (job #" +
                    data.job.id + ").",
                    "success"
                );

                if (mediaLink && data.media?.id) {
                    mediaLink.hidden = false;
                    mediaLink.href = "/content-studio/media";
                }


                console.log(
                    "Generation job created:",
                    data.job
                );

            }

            catch (error) {

                console.error(
                    "Generation failed:",
                    error
                );


                setProgress(
                    0,
                    "Failed"
                );


                setMessage(
                    error.message ||
                    "Unable to start generation.",
                    "error"
                );

            }

            finally {

                setButtonLoading(false);
            }

        }
    );


    // ======================================================
    // INITIAL STATE
    // ======================================================

    refreshPrompt();


    if (progress) {

        progress.classList.remove(
            "is-visible"
        );
    }


    if (progressBar) {

        progressBar.style.width =
            "0%";
    }


    if (percent) {

        percent.textContent =
            "0%";
    }


    if (status) {

        status.textContent =
            "Ready";
    }


    setMessage("", null);

});
