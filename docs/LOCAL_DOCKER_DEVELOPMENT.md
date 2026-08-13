# Local Docker development

The local Compose file deliberately runs immutable application code copied into
the `web` image. It does not bind-mount Python source, templates, static files,
or translations. This keeps local runtime behaviour close to production, but a
source change requires rebuilding `web` before it can appear at
`http://127.0.0.1:5000`.

## Development workflow

From the repository root, use the explicit rebuild workflow after changing
application source, templates, static assets, translations, or dependencies:

```powershell
docker compose build web
docker compose up -d --no-deps --force-recreate web
docker compose ps
```

Use a no-cache rebuild only when Docker-layer cache behaviour itself needs to
be ruled out:

```powershell
docker compose build --no-cache web
docker compose up -d --no-deps --force-recreate web
```

Do not use `docker compose down -v` for normal development: it removes the
local PostgreSQL volume. The commands above recreate only the application
service and preserve the database, logs, data, files, and test artifacts.

## Production workflow

Production remains image-based and must not bind-mount source code. Follow
the commands and release checks in [VPS_DEPLOYMENT_CHECKLIST.md](VPS_DEPLOYMENT_CHECKLIST.md), using the production Compose file and production environment file.

## Parity check

After a rebuild, verify both source and rendered HTML. On Windows PowerShell:

```powershell
docker compose exec -T web sh -c 'grep -nE "home-hbot-context|home-report-preview" /app/templates/index.html'
curl.exe -sS http://127.0.0.1:5000/ | Select-String 'home-hbot-context|home-report-preview'
```

Run the command within `sh -c` so Git Bash/MSYS does not rewrite `/app` paths.
