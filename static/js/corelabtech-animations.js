// Put this file in: static/js/corelabtech-animations.js

document.addEventListener("DOMContentLoaded", () => {

    // Reveal on scroll
    const revealItems = document.querySelectorAll("[data-reveal]");

    if ("IntersectionObserver" in window) {

        const observer = new IntersectionObserver((entries) => {

            entries.forEach((entry) => {

                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }

            });

        }, {
            threshold: 0.16
        });

        revealItems.forEach(item => observer.observe(item));

    } else {

        revealItems.forEach(item => item.classList.add("is-visible"));

    }

    // Animated counters

    document.querySelectorAll("[data-counter]").forEach(counter => {

        const target = parseInt(counter.dataset.counter, 10);

        let value = Math.max(0, target - 12);

        const step = Math.max(1, Math.ceil((target - value) / 18));

        const timer = setInterval(() => {

            value = Math.min(target, value + step);

            counter.textContent = value;

            if (value >= target) {
                clearInterval(timer);
            }

        }, 45);

    });

});