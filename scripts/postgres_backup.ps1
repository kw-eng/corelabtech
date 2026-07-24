param(
    [string]$OutputDir = "backups/postgres"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Run this script on the VPS or local machine with Docker installed."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$containerPath = "/tmp/corelabtech_$timestamp.dump"
$outputPath = Join-Path $OutputDir "corelabtech_$timestamp.dump"

docker compose exec -T db sh -lc "pg_dump -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -Fc -f $containerPath"
docker cp "corelabtech_postgres:$containerPath" $outputPath
docker compose exec -T db rm -f $containerPath

Write-Host "Backup created: $outputPath"
