(() => {
    const header = document.querySelector("header");
    const toggle = document.querySelector(".mobile-nav-toggle");
    const navigation = document.getElementById("primary-navigation");

    if (!header || !toggle || !navigation) return;

    header.classList.add("navigation-ready");
    const close = () => {
        header.classList.remove("navigation-open");
        toggle.setAttribute("aria-expanded", "false");
    };
    const open = () => {
        header.classList.add("navigation-open");
        toggle.setAttribute("aria-expanded", "true");
    };

    toggle.addEventListener("click", () => header.classList.contains("navigation-open") ? close() : open());
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            close();
            toggle.focus();
        }
    });
    document.addEventListener("click", (event) => {
        if (header.classList.contains("navigation-open") && !header.contains(event.target)) close();
    });
    navigation.addEventListener("click", (event) => {
        if (event.target.closest("a")) close();
    });
})();
