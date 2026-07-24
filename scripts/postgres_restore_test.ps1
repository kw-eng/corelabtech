param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,

    [string]$TestDatabase = "corelabtech_restore_test"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Run this script on the VPS or local machine with Docker installed."
}

if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "Backup file not found: $BackupPath"
}

$containerPath = "/tmp/corelabtech_restore_test.dump"

docker cp $BackupPath "corelabtech_postgres:$containerPath"
docker compose exec -T db sh -lc "dropdb -U `"`$POSTGRES_USER`" --if-exists $TestDatabase"
docker compose exec -T db sh -lc "createdb -U `"`$POSTGRES_USER`" $TestDatabase"
docker compose exec -T db sh -lc "pg_restore -U `"`$POSTGRES_USER`" -d $TestDatabase --no-owner $containerPath"
docker compose exec -T db sh -lc "psql -U `"`$POSTGRES_USER`" -d $TestDatabase -c `"SELECT COUNT(*) AS users_count FROM users;`""
docker compose exec -T db rm -f $containerPath

Write-Host "Restore test completed in database: $TestDatabase"
