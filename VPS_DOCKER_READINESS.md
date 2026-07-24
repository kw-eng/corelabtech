# CoreLabTech VPS / Docker Readiness

## 1. Local Docker run

```powershell
docker compose up --build
```

Health check:

```powershell
curl http://127.0.0.1:5000/api/health
```

The response should include `status=ok`, `database=ok`, disabled debug routes,
configured CORS for production, secure cookies for production and enabled rate limiting.

Manual smoke flow:

1. Login.
2. Create or select a subject.
3. Upload HR/HRV Timeline file.
4. Upload SpO2/Pulse Timeline file.
5. Synchronize timelines.
6. Run wellness analysis.
7. Open latest AI result.
8. Open subject trend.
9. Generate PDF report.

## 2. Production environment

Use `.env.production.example` as the template for the real VPS `.env`.

Required production values:

- `SECRET_KEY`: long random value.
- `DATABASE_URL`: PostgreSQL connection string for the `db` service.
- `APP_ENV=production`
- `FLASK_ENV=production`
- `PERFORMANCE_TESTING=false`
- `DISABLE_DEBUG_ROUTES=true`
- `CORS_ORIGINS=https://your-domain.example`
- `SESSION_COOKIE_SECURE=True`

Generate a strong secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 3. PostgreSQL backup

Create backup:

```powershell
.\scripts\postgres_backup.ps1
```

Test restore into a separate database:

```powershell
.\scripts\postgres_restore_test.ps1 -BackupPath .\backups\postgres\corelabtech_YYYYMMDD_HHMMSS.dump
```

Restore production database from backup:

```powershell
.\scripts\postgres_restore.ps1 -BackupPath .\backups\postgres\corelabtech_YYYYMMDD_HHMMSS.dump
```

Run backup daily on VPS with cron, systemd timer, Windows Task Scheduler, or hosting scheduler.

## 4. HTTPS / reverse proxy

Use `nginx/corelabtech.conf` as the starting Nginx config.

Before deployment:

- replace `your-domain.example` with the real domain,
- issue Let's Encrypt certificates,
- set `CORS_ORIGINS` and `PLAYWRIGHT_BASE_URL` to the same HTTPS origin,
- keep `SESSION_COOKIE_SECURE=True`,
- restrict direct access to port `5000` with firewall rules if Nginx is public.

## 5. Wellness report

The PDF report should contain:

- subject/session identification,
- PRE / DURING / POST measurements,
- HR/HRV Timeline samples,
- SpO2/Pulse Timeline samples,
- synchronized sample count,
- wellness status,
- data quality score and warnings,
- wellness-only disclaimer.
