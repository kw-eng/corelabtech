param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Run this script on the VPS or local machine with Docker installed."
}

if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "Backup file not found: $BackupPath"
}

$containerPath = "/tmp/corelabtech_restore.dump"

docker cp $BackupPath "corelabtech_postgres:$containerPath"
docker compose exec -T db sh -lc "pg_restore -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" --clean --if-exists --no-owner $containerPath"
docker compose exec -T db rm -f $containerPath

Write-Host "Restore completed from: $BackupPath"
