param(
    [string]$Target = "D:\corelabtech_PWA"
)

$ErrorActionPreference = "Stop"

$Source = Resolve-Path (Join-Path $PSScriptRoot "..")
$TargetPath = [System.IO.Path]::GetFullPath($Target)
$SourcePath = [System.IO.Path]::GetFullPath($Source)

if ($TargetPath -eq $SourcePath) {
    throw "Target must be different from source."
}

New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null

$excludedDirs = @(
    ".git",
    ".agents",
    ".codex",
    "__pycache__",
    "node_modules",
    "logs",
    "files",
    "test-results",
    "playwright-report",
    "backup_before_postgres",
    "backups"
)

$excludedFiles = @(
    ".env",
    ".env.local",
    ".env.test",
    "*.pyc",
    "~$*"
)

$robocopyArgs = @(
    $SourcePath,
    $TargetPath,
    "/E",
    "/NFL",
    "/NDL",
    "/NJH",
    "/NJS",
    "/NP",
    "/XD"
) + $excludedDirs + @("/XF") + $excludedFiles

robocopy @robocopyArgs | Out-Null

if ($LASTEXITCODE -gt 7) {
    throw "Robocopy failed with exit code $LASTEXITCODE."
}

$manifest = @'
{
  "name": "CoreLabTech Recovery",
  "short_name": "CoreLabTech",
  "description": "Mobile recovery, HBOT and physiology session tracker for wearable FIT and pulse oximeter data.",
  "id": "/?source=pwa",
  "start_url": "/?source=pwa",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#020617",
  "theme_color": "#00ffcc",
  "categories": ["health", "fitness", "productivity"],
  "icons": [
    {
      "src": "/static/img/logo.svg",
      "sizes": "any",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ],
  "shortcuts": [
    {
      "name": "Start Session",
      "short_name": "Session",
      "url": "/chamber",
      "description": "Capture a PRE, DURING and POST physiology session."
    },
    {
      "name": "Mission Control",
      "short_name": "Reports",
      "url": "/research",
      "description": "Review synchronized telemetry and AI summaries."
    }
  ]
}
'@

$serviceWorker = @'
const CACHE_NAME = "corelabtech-pwa-v1";

const APP_SHELL = [
  "/",
  "/offline",
  "/manifest.webmanifest",
  "/static/css/style.css",
  "/static/js/pwa.js",
  "/static/img/logo.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("/offline")))
    );
    return;
  }

  if (url.origin === location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            return response;
          })
          .catch(() => cached);

        return cached || network;
      })
    );
  }
});
'@

$pwaJs = @'
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/service-worker.js").catch(function (error) {
        console.warn("CoreLabTech PWA registration failed:", error);
      });
    });
  }

  function setOnlineState() {
    document.documentElement.classList.toggle("is-offline", !navigator.onLine);
  }

  window.addEventListener("online", setOnlineState);
  window.addEventListener("offline", setOnlineState);
  setOnlineState();
})();
'@

$offlineTemplate = @'
{% extends "layout.html" %}

{% block content %}

<section class="offline-page">
    <span class="page-eyebrow">Offline Mode</span>
    <h1>CoreLabTech is offline</h1>
    <p>
        The app shell is available, but live session data, uploads and reports
        need a network connection to synchronize safely.
    </p>
    <a href="{{ url_for('main.home') }}">Return to home</a>
</section>

{% endblock %}
'@

Set-Content -LiteralPath (Join-Path $TargetPath "static\manifest.webmanifest") -Value $manifest -Encoding UTF8
Set-Content -LiteralPath (Join-Path $TargetPath "static\service-worker.js") -Value $serviceWorker -Encoding UTF8
New-Item -ItemType Directory -Force -Path (Join-Path $TargetPath "static\js") | Out-Null
Set-Content -LiteralPath (Join-Path $TargetPath "static\js\pwa.js") -Value $pwaJs -Encoding UTF8
Set-Content -LiteralPath (Join-Path $TargetPath "templates\offline.html") -Value $offlineTemplate -Encoding UTF8

$layoutPath = Join-Path $TargetPath "templates\layout.html"
$layout = Get-Content -LiteralPath $layoutPath -Raw

if ($layout -notmatch 'name="viewport"') {
    $layout = $layout -replace '<meta charset="UTF-8">', '<meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#00ffcc">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="CoreLabTech">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="{{ url_for(''main.pwa_manifest'') }}">
    <link rel="apple-touch-icon" href="{{ url_for(''static'', filename=''img/logo.svg'') }}">'
}

if ($layout -notmatch 'static'', filename=''js/pwa.js') {
    $layout = $layout -replace '</body>', '    <script defer src="{{ url_for(''static'', filename=''js/pwa.js'') }}?v=pwa-20260721"></script>
</body>'
}

Set-Content -LiteralPath $layoutPath -Value $layout -Encoding UTF8

$mainRoutesPath = Join-Path $TargetPath "routes\main_routes.py"
$mainRoutes = Get-Content -LiteralPath $mainRoutesPath -Raw

$mainRoutes = $mainRoutes -replace 'from flask import \(\s*Blueprint,\s*render_template\s*\)', 'from flask import (
    Blueprint,
    current_app,
    render_template
)'

if ($mainRoutes -notmatch 'def offline') {
    $mainRoutes += @'


@main_bp.route("/offline")
def offline():
    return render_template("offline.html")


@main_bp.route("/manifest.webmanifest")
def pwa_manifest():
    response = current_app.send_static_file("manifest.webmanifest")
    response.headers["Content-Type"] = "application/manifest+json"
    return response


@main_bp.route("/service-worker.js")
def service_worker():
    response = current_app.send_static_file("service-worker.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    return response
'@
}

Set-Content -LiteralPath $mainRoutesPath -Value $mainRoutes -Encoding UTF8

$stylePath = Join-Path $TargetPath "static\css\style.css"
$style = Get-Content -LiteralPath $stylePath -Raw

if ($style -notmatch 'offline-page') {
    $style += @'

/* =========================
PWA / MOBILE APP
========================= */

.is-offline body::before{
    background:#facc15;
    color:#111827;
    content:"Offline mode";
    display:block;
    font-size:12px;
    font-weight:800;
    padding:8px 14px;
    text-align:center;
}

.offline-page{
    background:#020617;
    border:1px solid #1f3448;
    border-radius:8px;
    max-width:760px;
    padding:32px;
}

.offline-page h1{
    color:#f8fafc;
    font-size:40px;
    line-height:1.05;
    margin:0 0 14px;
}

.offline-page p{
    color:#b6c5d6;
    line-height:1.6;
    margin:0 0 24px;
}

.offline-page a{
    background:#00ffcc;
    border-radius:6px;
    color:#001014;
    display:inline-flex;
    font-weight:800;
    padding:12px 16px;
    text-decoration:none;
}

@media(max-width:700px){
    header{
        padding:14px;
    }

    .logo{
        height:82px;
    }

    .container{
        padding:22px 16px;
    }

    nav a,
    .nav-dropdown button{
        min-height:40px;
    }
}
'@
}

Set-Content -LiteralPath $stylePath -Value $style -Encoding UTF8

Write-Output "PWA copy ready: $TargetPath"
