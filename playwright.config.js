module.exports = {

    testDir .tests,

    timeout 30000,

    fullyParallel true,

    reporter [
        ['list'],
        ['html', { outputFolder 'playwright-report' }]
    ],

    use {
        baseURL http127.0.0.15000,
        headless true,
        viewport {
            width 1440,
            height 900
        },
        ignoreHTTPSErrors true,
        screenshot 'only-on-failure',
        video 'retain-on-failure',
        trace 'retain-on-failure'
    },

    webServer {
        command 'python app.py',
        url 'http127.0.0.15000',
        reuseExistingServer true,
        timeout 120000
    }
}
