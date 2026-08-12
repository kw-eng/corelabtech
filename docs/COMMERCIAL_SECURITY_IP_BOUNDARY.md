# Commercial Security and IP Boundary

## Trust boundary

The browser is a presentation client. Flask services remain authoritative for
session workflow, telemetry import, synchronization, data quality, wellness
response, longitudinal analysis, research interpretation, reports, public media
resolution, and optional AI narration.

The browser may receive measured values, chart-ready samples, localized
observations, confidence/completeness, trends, and authorized report/media
views. It must not require implementation rules, scoring thresholds, prompt
templates, storage paths, provider configuration, credentials, or private audit
metadata to render the product.

## Content Studio

Generation prompt construction is server-owned in
`services/prompt_builder_service.py`. Browser requests contain only validated
selection values. Generated Media responses use a presentation projection that
excludes prompts, negative prompts, file paths, notes, and owner identifiers.

Only administrators may directly register media or transition a media record to
`approved`, `published`, or final. This does not grant public publication: a
separate privileged public-role assignment remains required, as documented in
`PROMPT_9_3_PUBLIC_MEDIA_OPERATIONS.md`.

## Credentials and sessions

Example environment files use placeholders only. The database seed process
requires explicitly supplied E2E administrator and researcher passwords and
does not provide defaults. The historical committed-password maintenance script
is quarantined.

Production requires a non-default `SECRET_KEY`. Flask session and remember
cookies are HttpOnly, SameSite-configured, and secure when production transport
is configured for HTTPS.

## HTTP and error policy

Responses carry MIME, frame, referrer, CSP, and permissions policies. HSTS is
added only when `APP_ENV`/`FLASK_ENV` is production; production deployment must
terminate TLS before forwarding requests to Flask.

Research-route 500 responses are generic. Exception detail remains in
server-side logs and must not be reflected to a customer browser.

## CSRF migration policy

The complete route inventory is maintained in `CSRF_EXEMPTION_INVENTORY.md`.
Admin account mutations now use normal CSRF protection. Remaining legacy
browser endpoints are deliberately queued as individually testable client
migrations; they are not silently mass-changed because their current callers
do not yet provide a token header.

## Known limitations and follow-up

- The legacy latest-analysis compatibility endpoint now returns an explicit
  browser-safe presentation DTO and a reconstructed compatibility envelope.
  New consumers must depend only on documented presentation fields; internal
  analysis persistence structures remain server-side.
- Several legacy research JSON routes use explicit CSRF exemptions. Audit and
  remove each exemption only after confirming its client request contract.
- Limiter storage is currently process-local (`memory://`). Production multi-
  instance deployment requires a shared limiter store.
- Chromium E2E execution is a release gate and must run in CI/a host that can
  launch Chromium; local `spawn EPERM` is not a passing result.
