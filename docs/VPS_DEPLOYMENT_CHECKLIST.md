# CoreLabTech VPS deployment checklist

## Prerequisites

- Linux VPS with Docker Engine and Docker Compose.
- DNS `A/AAAA` record pointing the selected domain to the VPS.
- Firewall allowing inbound TCP 80 and 443 only; SSH restricted administratively.
- An off-server destination for encrypted backups.

## First deployment

1. Copy `deploy/vps/.env.production.example` to
   `deploy/vps/.env.production`.
2. Replace every placeholder, including a random `SECRET_KEY` of at least
   64 characters and a unique PostgreSQL password.
3. Set `CORS_ORIGINS=https://<domain>` and `SESSION_COOKIE_SECURE=True`.
4. Validate configuration:

   ```bash
   docker compose --env-file deploy/vps/.env.production \
     -f deploy/vps/docker-compose.yml config
   ```

5. Start database, application and automatic backup worker:

   ```bash
   docker compose --env-file deploy/vps/.env.production \
     -f deploy/vps/docker-compose.yml up -d db web backup
   ```

6. Apply schema and migrations:

   ```bash
   docker compose --env-file deploy/vps/.env.production \
     -f deploy/vps/docker-compose.yml exec web python run_database_setup.py
   ```

7. Before starting Nginx, issue the first certificate while port 80 is free:

   ```bash
   docker compose --env-file deploy/vps/.env.production \
     -f deploy/vps/docker-compose.yml --profile certificate run \
     --rm --service-ports certbot
   ```

8. Start HTTPS proxy:

   ```bash
   docker compose --env-file deploy/vps/.env.production \
     -f deploy/vps/docker-compose.yml up -d nginx
   ```

9. Verify `/api/health`, login, cookies, CORS and the complete UAT flow over HTTPS.

## Backup and restore

The `backup` service writes an encrypted-volume-ready PostgreSQL dump on the
configured interval and enforces `BACKUP_RETENTION_DAYS`. Its local volume is
not an off-server backup: copy the generated dumps to an encrypted remote
destination under the organization's approved backup policy.

Run a restore test after the first backup and at least monthly:

```bash
./scripts/postgres_restore_test.sh /srv/corelabtech-backups/corelabtech_YYYYMMDD_HHMMSS.dump
```

Backups must also be copied off the VPS. A backup is not accepted until the
restore test completes successfully.

## Certificate renewal

Configure a monthly renewal using the shared certificate volume and reload
Nginx after a successful renewal. Verify expiry monitoring separately.

## Release gate

- Database backup and restore test passed.
- HTTPS certificate valid with HTTP redirect.
- PostgreSQL has no public host port.
- Debug routes and performance mode disabled.
- Production secrets differ from examples and development.
- UAT signed by the facility operator.
- Data-processing agreement and retention policy approved.
- Rollback image/tag and database backup recorded.
