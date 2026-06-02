# Tutorial — Migracja CoreLabTech z SQLite do PostgreSQL

## 1. Cel migracji

Migracja projektu **CoreLabTech** z SQLite do PostgreSQL ma na celu przygotowanie systemu do pracy w architekturze zbliżonej do produkcyjnej.

SQLite sprawdza się dobrze na etapie prototypu, ale przy projekcie typu:

- HBOT telemetry pipeline,
- FIT + CSV ingestion,
- AI analysis,
- AI QA Lab,
- Playwright E2E,
- Gatling performance tests,
- przyszłe logowanie i role,
- cloud deployment,

lepszym wyborem jest PostgreSQL.

PostgreSQL umożliwia:

- stabilną pracę wielu użytkowników,
- role i autoryzację,
- bezpieczne relacje między tabelami,
- foreign keys,
- indeksy,
- lepszą wydajność,
- Docker / cloud deployment,
- monitoring,
- backupy,
- produkcyjne wdrożenie.

---

## 2. Architektura po migracji

```text
Browser / UI
    ↓
Flask API
    ↓
PostgreSQL
    ↓
AI Analysis / Telemetry / QA / Performance
```

Docelowo projekt działa jako platforma:

```text
CoreLabTech
├── Flask API
├── PostgreSQL
├── AI Engine
├── Playwright QA
├── Gatling Performance
├── HBOT Telemetry
├── FIT + CSV Merge Engine
├── Research Dashboard
├── AI QA Lab
└── Performance Testing Layer
```

---

## 3. Utworzenie bazy PostgreSQL w pgAdmin 4

### 3.1. Otwórz pgAdmin 4

Po lewej stronie:

```text
Servers
→ PostgreSQL
```

Zaloguj się hasłem ustawionym podczas instalacji PostgreSQL.

### 3.2. Utwórz bazę danych

Kliknij prawym przyciskiem:

```text
Databases
→ Create
→ Database
```

Ustaw:

```text
Database: corelabtech
Owner: postgres
```

Kliknij:

```text
Save
```

### 3.3. Utwórz użytkownika aplikacji

Kliknij prawym przyciskiem:

```text
Login/Group Roles
→ Create
→ Login/Group Role
```

Zakładka **General**:

```text
Name: corelabtech_user
```

Zakładka **Definition**:

```text
Password: corelabtech_password
```

Zakładka **Privileges**:

```text
Can login: YES
```

Kliknij:

```text
Save
```

### 3.4. Nadaj uprawnienia

Kliknij bazę:

```text
corelabtech
```

Następnie:

```text
Tools
→ Query Tool
```

Wykonaj:

```sql
GRANT ALL PRIVILEGES
ON DATABASE corelabtech
TO corelabtech_user;

GRANT ALL ON SCHEMA public
TO corelabtech_user;

ALTER SCHEMA public
OWNER TO corelabtech_user;
```

---

## 4. Plik `.env`

W katalogu głównym projektu utwórz plik:

```text
.env
```

Przykładowa zawartość:

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=corelabtech-super-secret-key-change-this

DATABASE_URL=postgresql://corelabtech_user:corelabtech_password@localhost:5432/corelabtech
PGCLIENTENCODING=UTF8

SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=False
REMEMBER_COOKIE_HTTPONLY=True
PERMANENT_SESSION_LIFETIME_MINUTES=60

UPLOAD_FOLDER=data/uploads
MAX_CONTENT_LENGTH=52428800
MAX_FIT_UPLOAD_MB=100
MAX_CSV_UPLOAD_MB=20

PLAYWRIGHT_BASE_URL=http://127.0.0.1:5000
GATLING_REPORTS_PATH=tests/performance/gatling/target/gatling

AI_MODE=research
AI_ENABLE_ANOMALY=True
AI_ENABLE_TRENDS=True

LOG_LEVEL=DEBUG
APP_ENV=local
```

Do `.gitignore` dodaj:

```text
.env
```

---

## 5. Instalacja bibliotek Python

Uruchom:

```bash
pip install psycopg2-binary python-dotenv werkzeug
```

Do `requirements.txt` dodaj:

```text
psycopg2-binary
python-dotenv
werkzeug
```

---

## 6. Plik `database_postgres.py`

Utwórz plik:

```text
database_postgres.py
```

Zawartość:

```python
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def db():

    os.environ["PGCLIENTENCODING"] = "UTF8"

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL missing")

    return psycopg2.connect(
        database_url,
        client_encoding="UTF8"
    )
```

---

## 7. Inicjalizacja schematu PostgreSQL

Plik:

```text
init_postgres_db.py
```

tworzy główne tabele:

- `users`,
- `tests`,
- `fit_data`,
- `csv_data`,
- `full_sessions`.

Tworzy też indeksy oraz foreign keys.

Uruchom:

```bash
python init_postgres_db.py
```

Oczekiwany wynik:

```text
PostgreSQL database initialized successfully.
```

---

## 8. Seed użytkowników

Plik:

```text
seed_postgres_db.py
```

tworzy podstawowe role:

```text
viewer
operator
researcher
admin
```

Uruchom:

```bash
python seed_postgres_db.py
```

Przykładowe konta:

```text
admin@corelabtech.local / Admin123!
operator@corelabtech.local / Operator123!
researcher@corelabtech.local / Researcher123!
viewer@corelabtech.local / Viewer123!
```

---

## 9. Sprawdzenie bazy

Plik:

```text
check_postgres_db.py
```

Uruchom:

```bash
python check_postgres_db.py
```

Oczekiwany wynik po seedzie:

```text
users: 4
tests: 0
fit_data: 0
csv_data: 0
full_sessions: 0
```

---

## 10. Migracja SQLite do PostgreSQL

Plik:

```text
migrate_sqlite_to_postgres.py
```

kopiuje dane z SQLite:

```text
data/database.db
```

do PostgreSQL.

Migrowane tabele:

- `users`,
- `tests`,
- `fit_data`,
- `csv_data`,
- `full_sessions`.

Uruchom:

```bash
python migrate_sqlite_to_postgres.py
```

Przykładowy poprawny wynik:

```text
Migrating users: 1 rows
Ensuring missing users: 2 user_ids found
Migrating tests: 7 rows
Migrating fit_data: 1342 rows
Migrating csv_data: 1723 rows
Migrating full_sessions: 7 rows
----------------------------------------
SQLite to PostgreSQL migration completed.
```

Po migracji ponownie uruchom:

```bash
python check_postgres_db.py
```

---

## 11. Backup przed przepięciem aplikacji

Przed zmianą kodu z SQLite na PostgreSQL wykonaj backup.

W Git Bash:

```bash
mkdir -p backup_before_postgres/routes
mkdir -p backup_before_postgres/data

cp database.py backup_before_postgres/database.py
cp data/database.db backup_before_postgres/data/database.db
cp routes/*.py backup_before_postgres/routes/
```

Backup powinien zawierać starą wersję SQLite, czyli z placeholderami:

```python
?
```

Aktywne pliki projektu po migracji mają mieć placeholdery PostgreSQL:

```python
%s
```

---

## 12. Przepięcie importów DB

W route’ach zmień:

```python
from database import db
```

na:

```python
from database_postgres import db
```

Sprawdź szczególnie:

```text
routes/research_routes.py
routes/upload_routes.py
routes/telemetry_routes.py
routes/user_routes.py
routes/ai_routes.py
routes/api_routes.py
routes/qa_routes.py
routes/ai_qa_routes.py
routes/performance_routes.py
```

---

## 13. Zamiana placeholderów SQL

SQLite:

```python
WHERE session_id=?
```

PostgreSQL:

```python
WHERE session_id=%s
```

SQLite:

```python
VALUES (?, ?, ?)
```

PostgreSQL:

```python
VALUES (%s, %s, %s)
```

Dynamiczne placeholdery:

```python
placeholders = ",".join(["?"] * len(session_ids))
```

zamień na:

```python
placeholders = ",".join(["%s"] * len(session_ids))
```

---

## 14. Usunięcie pozostałości SQLite

Po migracji usuń albo przerób:

```python
import sqlite3
```

```python
con.row_factory = sqlite3.Row
```

```sql
AUTOINCREMENT
```

```sql
INSERT OR REPLACE
```

```sql
datetime('now')
```

Zamienniki PostgreSQL:

```sql
id SERIAL PRIMARY KEY
```

```sql
CURRENT_TIMESTAMP
```

```sql
INSERT INTO table (...)
VALUES (...)
ON CONFLICT (key)
DO UPDATE SET ...
```

---

## 15. Usunięcie `ensure_tables()`

Po migracji na PostgreSQL nie twórz tabel podczas requestu.

Usuń wywołania:

```python
ensure_tables()
```

z endpointów typu:

```text
/chamber
/upload_csv
/upload_fit
/api/fit_data
/api/csv_data
/api/fit_timeseries/<session_id>
```

Docelowo usuń też całą funkcję:

```python
def ensure_tables():
    ...
```

Schemat bazy ma być tworzony tylko przez:

```text
init_postgres_db.py
```

---

## 16. Foreign keys i automatyczne tworzenie usera

Po dodaniu foreign key endpointy upload/save mogą zwrócić błąd, jeśli `user_id` nie istnieje.

Dlatego przed insertem do `csv_data`, `fit_data` lub `full_sessions` dodaj:

```python
c.execute("""
    INSERT INTO users (
        user_id,
        subject_id,
        role,
        is_active,
        notes
    )
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (user_id) DO NOTHING
""", (
    user_id,
    user_id,
    "operator",
    True,
    "Auto-created during upload or session save"
))
```

Dodaj to w:

- `upload_csv()`,
- `upload_fit()`,
- `save_full_session()`.

---

## 17. Test ręczny endpointów

Uruchom Flask:

```bash
python app.py
```

Sprawdź:

```text
http://127.0.0.1:5000/chamber
http://127.0.0.1:5000/api/sessions
http://127.0.0.1:5000/debug/db
```

Test POST:

```bash
curl -X POST http://127.0.0.1:5000/api/run_analysis \
  -H "Content-Type: application/json" \
  -d '{"session_id":"SESSION_ID"}'
```

---

## 18. Test Playwright

Najpierw tylko chamber flow:

```bash
npx playwright test tests/e2e/chamber_flow.spec.ts
```

Oczekiwany wynik końcowy:

```text
7 passed
```

Następnie pełny suite:

```bash
npx playwright test
```

Oczekiwany wynik:

```text
11 passed
```

Potwierdzony wynik po migracji:

```text
11 passed (16.3s)
```

Oznacza to, że działają:

- `/chamber`,
- `/api/sessions`,
- `/upload_csv`,
- `/api/during_merge`,
- `/api/save_full_session`,
- `/api/run_analysis`,
- `/api/user_trends`,
- `AI QA Lab`.

---

## 19. Test Gatling

Przejdź do katalogu:

```bash
cd tests/performance/gatling
```

Uruchom:

```bash
mvn gatling:test -Dgatling.simulationClass=corelabtech.SessionsSimulation
mvn gatling:test -Dgatling.simulationClass=corelabtech.DuringMergeSimulation
mvn gatling:test -Dgatling.simulationClass=corelabtech.RunAnalysisSimulation
mvn gatling:test -Dgatling.simulationClass=corelabtech.UploadCsvSimulation
mvn gatling:test -Dgatling.simulationClass=corelabtech.UploadFitSimulation
```

---

## 20. Poprawka `pom.xml` dla Gatling

Jeżeli Maven zawsze uruchamia `SessionsSimulation`, mimo że podajesz inną klasę:

```bash
-Dgatling.simulationClass=corelabtech.DuringMergeSimulation
```

usuń z `pom.xml`:

```xml
<configuration>
    <simulationClass>corelabtech.SessionsSimulation</simulationClass>
</configuration>
```

Poprawny plugin:

```xml
<plugin>
    <groupId>io.gatling</groupId>
    <artifactId>gatling-maven-plugin</artifactId>
    <version>${gatling.maven.plugin.version}</version>
</plugin>
```

Po zmianie:

```bash
mvn clean test-compile
```

---

## 21. Potwierdzone wyniki Gatling po migracji

### Sessions API

```text
OK = 170
KO = 0
P95 = 214–228 ms
Success rate = 100%
Gate P95 < 500 ms = true
```

### During Merge

```text
OK = 100
KO = 0
P95 = 224 ms
Gate P95 < 1000 ms = true
Failed events < 10% = true
```

### AI Run Analysis

```text
OK = 70
KO = 0
P95 = 233 ms
Success rate = 100%
Gate P95 < 1500 ms = true
```

### CSV Upload

```text
OK = 35
KO = 0
P95 = 248 ms
Success rate = 100%
Gate P95 < 2000 ms = true
```

### FIT Upload

```text
OK = 35
KO = 0
P95 = 212 ms
Failed events = 0%
Gate P95 < 2500 ms = true
```

---

## 22. Typowe błędy i rozwiązania

### `Method Not Allowed`

Endpoint działa, ale wywołujesz GET zamiast POST.

### `sqlite3.OperationalError near "%"`

Masz SQL PostgreSQL, ale aplikacja nadal używa SQLite connection.

Napraw:

```python
from database_postgres import db
```

### `psycopg2.errors.SyntaxError near "?"`

Masz PostgreSQL connection, ale zostały placeholdery SQLite.

Napraw:

```python
? → %s
```

### `psycopg2.errors.SyntaxError near "AUTOINCREMENT"`

Została składnia SQLite.

Napraw:

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
```

na:

```sql
id SERIAL PRIMARY KEY
```

### `ForeignKeyViolation`

Próbujesz zapisać rekord z `user_id`, którego nie ma w `users`.

Napraw przez:

```sql
INSERT INTO users (...)
ON CONFLICT (user_id) DO NOTHING
```

### Gatling uruchamia złą symulację

Usuń wymuszoną klasę z `pom.xml`:

```xml
<simulationClass>corelabtech.SessionsSimulation</simulationClass>
```

---

## 23. Checklist po migracji

Dodaj plik:

```text
postgres_migration_checklist.md
```

Zawartość:

```md
# PostgreSQL Migration Checklist

## DATABASE

- [x] PostgreSQL installed
- [x] corelabtech database created
- [x] corelabtech_user created
- [x] DB privileges granted
- [x] .env configured
- [x] psycopg2 installed

## DB INITIALIZATION

- [x] init_postgres_db.py
- [x] seed_postgres_db.py
- [x] check_postgres_db.py

## SQLITE → POSTGRES MIGRATION

- [x] migrate_sqlite_to_postgres.py
- [x] users migrated
- [x] tests migrated
- [x] fit_data migrated
- [x] csv_data migrated
- [x] full_sessions migrated

## TESTING

- [x] /chamber
- [x] /api/sessions
- [x] /upload_csv
- [x] /api/during_merge
- [x] /api/save_full_session
- [x] /api/run_analysis
- [x] /api/user_trends

## PLAYWRIGHT

- [x] chamber flow
- [x] AI QA Lab
- [x] full suite 11 passed

## GATLING

- [x] SessionsSimulation
- [x] DuringMergeSimulation
- [x] RunAnalysisSimulation
- [x] UploadCsvSimulation
- [x] UploadFitSimulation
```

---

## 24. Status końcowy migracji

Po wykonaniu migracji i testów system ma działające:

```text
PostgreSQL
Playwright E2E
Gatling Performance
AI Analysis
Telemetry Merge
FIT/CSV ingestion
Trend analysis
AI QA Lab
Chamber flow
```

Potwierdzony stan:

```text
Playwright: 11 passed
Gatling: all performance smoke simulations passed
```

---

## 25. Co dalej po PostgreSQL

Następny etap to zabezpieczenie systemu.

### Auth

- Flask-Login,
- `/login`,
- `/logout`,
- password hash,
- role_required.

### Role

```text
viewer      → podgląd własnych sesji
operator    → tworzenie sesji HBOT
researcher  → analiza AI, trendy, eksporty
admin       → QA, performance, DB, users
```

### Public pages

```text
/about
/technology
/qa
/performance-tests
```

### Login required

```text
/chamber
/research
/ai-lab
```

### Admin / Researcher

```text
/admin
/ai-qa-lab
/debug/db
/api/run_playwright
/api/performance/run
```

### Security

- upload validation,
- file size limits,
- allowed extensions,
- rate limiting,
- CSRF protection,
- secure cookies,
- HTTPS,
- production SECRET_KEY,
- disabled Flask debugger,
- database backups.

### Production

- Docker,
- Docker Compose,
- Gunicorn,
- Nginx,
- PostgreSQL container,
- cloud deployment AWS/Azure,
- monitoring Grafana/Prometheus.

---

## 26. Efekt końcowy

Po migracji projekt CoreLabTech przestaje być prototypem SQLite i staje się technicznie gotowy pod produkcyjną architekturę:

```text
production-ready AI telemetry & QA platform
```

z:

- PostgreSQL,
- enterprise QA,
- Playwright E2E,
- Gatling performance tests,
- FIT/CSV telemetry ingestion,
- AI analysis,
- trend analysis,
- role-ready users table,
- cloud readiness,
- security foundation.
