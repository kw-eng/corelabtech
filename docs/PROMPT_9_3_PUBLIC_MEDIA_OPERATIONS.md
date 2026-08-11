# Public Media Operations

## Implemented

Public website media is deliberately curated rather than automatically
published. `public_media_assets.role` is the one active mapping for a named
surface, such as `home.hero`, `technology.hero`, or `wellness.hero`.

A record resolves only when the mapped Generated Media record exists, is final,
has `approved` or `published` status, has an appropriate image/video MIME type,
and its local file is present. The read-only resolver returns presentation data
only: media type, MIME type, dimensions, localized alt text, and safe public
URL construction. It does not return prompts, owner identifiers, notes, or
storage paths.

The public route serves a verified local file by role. It accepts no media ID,
does not expose an ownership selector, and has no mutation methods.

## Lifecycle and authorization boundary

The lifecycle boundary is:

`Generated → Reviewed → Approved → privileged public-role assignment → public resolver`.

Generated Media ownership is not publishing permission. There is no public-role
write endpoint or self-service role UI in this increment, so anonymous users,
normal authenticated users, and media owners cannot place an asset on a public
page. A future write path must require `@role_required("admin")`, CSRF
protection, a final approved/published candidate, and an append-only
`audit_log` event with the actor, role, old mapping, new mapping, and outcome.

## Schema, deletion, and recovery

Migration 029 creates the mapping table. Forward-only migration 030 explicitly
sets both Generated Media foreign keys to `ON DELETE RESTRICT`, requires
non-blank English and Polish alt text, and refreshes `updated_at` on every
mapping update. Deleting a referenced media record is therefore blocked rather
than silently changing a public role or substituting another asset.

CoreLabTech migrations are forward-only; there is no downgrade convention. To
recover a bad assignment, an authorized operational procedure should update or
remove the mapping in a transaction and record the audit event. If a mapping is
missing, ineligible, or its file cannot be read, the page uses its configured
static vendor-neutral fallback. The resolver never chooses a different
generated asset automatically.

## Alt text

Informative public imagery requires meaningful `alt_text_en` and
`alt_text_pl`. Raw prompts and private metadata are never promoted to alt text.
Decorative media should use the established empty-alt convention only when it
is genuinely decorative; the current public role mappings are informative.

## Video

The public component supports verified MP4/WebM media with native controls,
`playsinline`, and `preload="metadata"`. It does not autoplay with sound or
load external URLs. Missing, ineligible, or unavailable videos fail closed and
the page fallback remains usable. Poster-role serving is not enabled yet;
invalid poster mappings do not expose a file or affect page rendering.

## Deferred

- Protected administrator UI/API for assigning public roles.
- Audit emission from that future assignment operation.
- Curated production video and poster assets.
- A DAM or broader Content Studio redesign.
