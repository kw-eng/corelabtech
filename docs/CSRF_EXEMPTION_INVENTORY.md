# CSRF Exemption Inventory

Reviewed for Prompt 9.4. CSRF applies to cookie-authenticated state changes;
read-only routes do not require an exemption. `MIGRATE_CLIENT_FIRST` means the
existing browser client currently omits a CSRF header and must be changed with
a focused regression before removing the exemption.

| Route | Method | Auth / caller | State-changing | Classification | Action / rationale |
|---|---|---|---:|---|---|
| `/api/ai_qa/run_test` | POST | researcher/admin, internal AI QA | Yes | MIGRATE_CLIENT_FIRST | Internal tool client needs CSRF-header migration. |
| `/api/ai_qa/generate_test` | POST | researcher/admin, internal AI QA | Yes | MIGRATE_CLIENT_FIRST | Internal tool client needs CSRF-header migration. |
| `/api/ai_qa/validate` | POST | researcher/admin, internal AI QA | Yes | MIGRATE_CLIENT_FIRST | Internal tool client needs CSRF-header migration. |
| `/api/qa/run_pipeline` | POST | researcher/admin, internal AI QA | Yes | MIGRATE_CLIENT_FIRST | Expensive subprocess trigger; preserve role/rate limit and migrate caller. |
| `/api/qa/run_playwright` | POST | admin, internal QA | Yes | MIGRATE_CLIENT_FIRST | Expensive subprocess trigger; migrate caller. |
| `/api/qa/run_qa_loop` | POST | admin, internal QA | Yes | MIGRATE_CLIENT_FIRST | Expensive subprocess trigger; migrate caller. |
| `/api/performance/run` | POST | admin, internal performance UI | Yes | MIGRATE_CLIENT_FIRST | Expensive subprocess trigger; migrate caller. |
| `/api/chambers` | POST | researcher/admin, chamber form | Yes | MIGRATE_CLIENT_FIRST | Existing form client lacks a token header. |
| `/api/client-programs` | GET/POST | staff, chamber form | POST only | MIGRATE_CLIENT_FIRST | Split GET/POST decorators during client migration. |
| `/api/client-programs/<id>` | PATCH | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Existing form client lacks a token header. |
| `/api/subjects`, `/api/users` | GET | staff, chamber form | No | NOT_APPLICABLE | Remove exemption when route decorators are next touched. |
| `/api/subjects`, `/api/users` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Existing form client lacks a token header. |
| `/api/delete_subject`, `/api/delete_user` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Destructive action; migrate with client regression. |
| `/upload_fit` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Upload client needs multipart CSRF header migration. |
| `/upload_csv` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Upload client needs multipart CSRF header migration. |
| `/api/telemetry/preflight` | POST | staff, chamber form | No persistence | MIGRATE_CLIENT_FIRST | Uploads temporary file only but uses authenticated cookie. |
| `/upload_telemetry` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | External telemetry import persists data. |
| `/api/during_merge` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Merge operation; migrate browser client. |
| `/api/save_phase` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | PRE/DURING/POST persistence; migrate browser client. |
| `/api/sessions/<id>/recovery-follow-up` | POST | staff, research dashboard | Yes | MIGRATE_CLIENT_FIRST | Recovery persistence; migrate browser client. |
| `/api/save_full_session` | POST | staff, chamber form | Yes | MIGRATE_CLIENT_FIRST | Session persistence; migrate browser client. |
| `/api/delete_sessions` | POST | admin, dashboard/form | Yes | MIGRATE_CLIENT_FIRST | Destructive action; migrate all callers together. |
| `/api/run_analysis` | POST | staff, dashboards/labs | Yes | MIGRATE_CLIENT_FIRST | Expensive analysis; current browser and E2E callers need token migration. |
| `/api/user_trends/<id>/narration` | POST | staff, research dashboard | Yes | MIGRATE_CLIENT_FIRST | Backend LLM request; migrate caller. |
| `/api/admin/accounts` | GET | admin, accounts UI | No | NOT_APPLICABLE | Exemption removed. |
| `/api/admin/accounts` | POST | admin, accounts UI | Yes | REMOVE_EXEMPTION | Implemented: browser now supplies `X-CSRFToken`. |
| `/api/admin/accounts/reset_password` | POST | admin, accounts UI | Yes | REMOVE_EXEMPTION | Implemented. |
| `/api/admin/accounts/update_role` | POST | admin, accounts UI | Yes | REMOVE_EXEMPTION | Implemented. |
| `/api/admin/accounts/toggle_active` | POST | admin, accounts UI | Yes | REMOVE_EXEMPTION | Implemented. |
| `/api/push_telemetry`, legacy aliases | POST/GET | authenticated legacy caller | No | KEEP_WITH_JUSTIFICATION | Endpoint returns HTTP 410 and does not process data. |

The public media resolver has no write route. Content Studio state-changing
routes already use normal Flask-WTF CSRF protection.
