# PostgreSQL Migration Checklist

## DATABASE

- [x] PostgreSQL installed
- [x] corelabtech database created
- [x] corelabtech_user created
- [x] DB privileges granted
- [x] .env configured
- [x] psycopg2 installed

---

## DB INITIALIZATION

- [x] init_postgres_db.py
- [x] seed_postgres_db.py
- [x] check_postgres_db.py

---

## SQLITE → POSTGRES MIGRATION

- [x] migrate_sqlite_to_postgres.py
- [x] users migrated
- [x] tests migrated
- [x] fit_data migrated
- [x] csv_data migrated
- [x] full_sessions migrated

---

## ROUTES PLACEHOLDERS

Replace:
? → %s

### ROUTES

- [ ] research_routes.py
- [ ] upload_routes.py
- [ ] telemetry_routes.py
- [ ] ai_routes.py
- [ ] ai_qa_routes.py
- [ ] api_routes.py
- [ ] performance_routes.py
- [ ] qa_routes.py
- [ ] user_routes.py
- [ ] publication_routes.py

---

## TESTING

### Flask

- [ ] /debug/db
- [ ] /api/sessions
- [ ] /api/users
- [ ] /api/run_analysis
- [ ] /api/during_merge
- [ ] /api/user_trends

### Uploads

- [ ] upload CSV
- [ ] upload FIT

### UI

- [ ] /research
- [ ] /ai-lab
- [ ] /ai-qa-lab
- [ ] /performance-tests

---

## PLAYWRIGHT

- [ ] playwright tests pass
- [ ] upload flow works
- [ ] AI analysis works
- [ ] QA dashboard works

---

## GATLING

- [ ] SessionsSimulation
- [ ] DuringMergeSimulation
- [ ] RunAnalysisSimulation
- [ ] UploadCsvSimulation
- [ ] UploadFitSimulation

---

## NEXT STEP

### AUTH

- [ ] Flask-Login
- [ ] login/logout
- [ ] role_required
- [ ] protected APIs
- [ ] protected admin pages

### SECURITY

- [ ] upload validation
- [ ] rate limiting
- [ ] CSRF
- [ ] HTTPS
- [ ] secure cookies

### PRODUCTION

- [ ] Docker
- [ ] PostgreSQL container
- [ ] Nginx
- [ ] Gunicorn
- [ ] Cloud deployment
- [ ] Monitoring