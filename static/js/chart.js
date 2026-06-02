// static/js/chart.js

let charts = {}

function destroyChart(name) {
    if (charts[name]) {
        charts[name].destroy()
        delete charts[name]
    }
}

function createLineChart(canvasId, label, labels, values) {

    destroyChart(canvasId)

    const canvas = document.getElementById(canvasId)

    if (!canvas) {
        console.error("Canvas not found:", canvasId)
        return
    }

    charts[canvasId] = new Chart(canvas, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    })
}