from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W_NS)


DOC_DIR = Path(r"D:\corelabtech_tutorials\wiedza_QA_WEB")


def qn(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def paragraph(text: str, style: str | None = None) -> ET.Element:
    p = ET.Element(qn("p"))
    if style:
        p_pr = ET.SubElement(p, qn("pPr"))
        ET.SubElement(p_pr, qn("pStyle"), {qn("val"): style})
    r = ET.SubElement(p, qn("r"))
    t = ET.SubElement(r, qn("t"))
    t.text = text
    return p


def body_text(root: ET.Element) -> str:
    return "\n".join(
        "".join(t.text or "" for t in p.iter(qn("t"))).strip()
        for p in root.iter(qn("p"))
    )


def append_section(docx_path: Path, marker: str, entries: list[tuple[str, str | None]]) -> bool:
    with TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        with zipfile.ZipFile(docx_path, "r") as zin:
            zin.extractall(temp)

        document_xml = temp / "word" / "document.xml"
        root = ET.parse(document_xml).getroot()
        text = body_text(root)

        if marker in text:
            return False

        body = root.find(qn("body"))
        if body is None:
            raise RuntimeError(f"Missing document body in {docx_path}")

        sect_pr = body.find(qn("sectPr"))
        insert_at = list(body).index(sect_pr) if sect_pr is not None else len(list(body))

        new_nodes = [paragraph("", None)]
        for entry_text, style in entries:
            new_nodes.append(paragraph(entry_text, style))

        for offset, node in enumerate(new_nodes):
            body.insert(insert_at + offset, node)

        ET.ElementTree(root).write(document_xml, encoding="utf-8", xml_declaration=True)

        backup = docx_path.with_suffix(
            f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        )
        shutil.copy2(docx_path, backup)

        with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for file_path in temp.rglob("*"):
                if file_path.is_file():
                    zout.write(file_path, file_path.relative_to(temp).as_posix())

    return True


def replace_text(docx_path: Path, replacements: dict[str, str]) -> bool:
    with TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        with zipfile.ZipFile(docx_path, "r") as zin:
            zin.extractall(temp)

        document_xml = temp / "word" / "document.xml"
        xml = document_xml.read_text(encoding="utf-8")
        original = xml
        for old, new in replacements.items():
            xml = xml.replace(old, new)

        if xml == original:
            return False

        backup = docx_path.with_suffix(
            f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        )
        shutil.copy2(docx_path, backup)
        document_xml.write_text(xml, encoding="utf-8")

        with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for file_path in temp.rglob("*"):
                if file_path.is_file():
                    zout.write(file_path, file_path.relative_to(temp).as_posix())

    return True


def update_scalone() -> None:
    path = DOC_DIR / "WIEDZA_PROJEKT_QA_SCALONE_FINAL.docx"
    replace_text(
        path,
        {
            "Umiesz wyjasnic migracje 004-010.": "Umiesz wyjasnic migracje 004-012, w tym ai_results, hrv_imports, hrv_intervals, session_features i daily_baselines.",
            "Migracje 004-010 odpalone.": "Migracje 004-012 odpalone przez jednolity runner migracji.",
            "rozumiec tabele 004-010,": "rozumiec tabele 004-012, w tym HRV, baseline i ai_results,",
            "Aktualizacja: 2026-07-24 08:22": "Aktualizacja: 2026-07-24 - wersja zsynchronizowana z wellness MVP i rozmowami technicznymi",
        },
    )

    marker = "AKTUALIZACJA MERYTORYCZNA 2026-07-24 - WERSJA DO ROZMOWY TECHNICZNEJ"
    entries = [
        (marker, "Heading1"),
        ("Cel tej aktualizacji", "Heading2"),
        ("Ten blok doprecyzowuje, jak uzywac pliku WIEDZA_PROJEKT_QA_SCALONE_FINAL razem z dokumentami Przygotowanie_do_rozmowy_technicznej_QA_Automation_FINAL oraz Przygotowanie_do_rozmowy_z_lektorka_angielski_FINAL. Plik scalony jest baza merytoryczna o projekcie, a dwa pozostale pliki sluza do treningu odpowiedzi i plynnosci wypowiedzi.", None),
        ("Jak uzywac trzech plikow", "Heading2"),
        ("1. WIEDZA_PROJEKT_QA_SCALONE_FINAL: uzywaj jako glownej encyklopedii projektu CoreLabTech, architektury, API, PostgreSQL, danych, security, test strategy i decyzji technicznych.", None),
        ("2. Przygotowanie_do_rozmowy_technicznej_QA_Automation_FINAL: uzywaj jako skryptu treningowego na ostatnie 24-48 godzin przed rozmowa techniczna. Tu cwicz krotkie odpowiedzi, framework automation, API, SQL, Docker, CI/CD i live coding.", None),
        ("3. Przygotowanie_do_rozmowy_z_lektorka_angielski_FINAL: uzywaj do mowienia na glos po angielsku. Celem jest naturalna komunikacja, STAR, autoprezentacja i proste wyjasnianie projektu.", None),
        ("Aktualny stan systemu CoreLabTech", "Heading2"),
        ("System jest obecnie ustawiany jako wellness/research MVP, a nie jako produkt kliniczny. Jezyk wynikow i raportow powinien mowic o wellness status, recovery trend, elevated load, oxygenation trend i data quality warning, bez sugerowania diagnozy medycznej.", None),
        ("Zrobione elementy, ktore warto umiec opisac na rozmowie: jednolity runner migracji ze schema_migrations, migracje 011 i 012, tabele hrv_imports, hrv_intervals, session_features i daily_baselines, podstawowe moduly trend_analysis, longitudinal_analysis i adaptation_analysis, raport PDF oparty o PostgreSQL oraz ai_results, a takze wellness aliases w wynikach analizy.", None),
        ("Wieksze prace pozostawione na pozniej: pelne wydzielenie subjects_routes.py i admin_routes.py z research_routes.py, pelny importer Garmin/Elite HRV, pelna aplikacja mobilna, zaawansowana analityka baseline na danych historycznych oraz certyfikacja kliniczna, jezeli produkt mialby wejsc poza wellness.", None),
        ("Gotowa odpowiedz techniczna EN - opis projektu", "Heading2"),
        ("CoreLabTech is a Python and Flask-based web application for session-based physiology and wellness data analysis. It imports FIT and CSV data, validates and stores them in PostgreSQL, merges synchronized measurements, calculates features, runs a deterministic wellness analysis and generates dashboards and PDF reports. From a QA automation perspective, the project is useful because it contains realistic API flows, database validation, file imports, data-quality checks, role-based access, Dockerized infrastructure and regression scenarios for Playwright/API tests.", None),
        ("Gotowa odpowiedz PL - opis projektu", "Heading2"),
        ("CoreLabTech to aplikacja webowa w Pythonie i Flasku do analizy danych sesyjnych w obszarze wellness. System importuje dane FIT i CSV, waliduje je, zapisuje w PostgreSQL, laczy pomiary w osi czasu, liczy cechy, uruchamia deterministyczna analize wellness i generuje dashboard oraz raport PDF. Z perspektywy QA Automation projekt jest dobrym materialem, bo zawiera realne przeplywy API, walidacje bazy danych, import plikow, jakosc danych, role uzytkownikow, Docker i scenariusze regresji UI/API.", None),
        ("Najwazniejsze punkty do powtorzenia przed rozmowa techniczna", "Heading2"),
        ("Umiej w 60-90 sekund opisac architekture: routes -> services -> repositories -> PostgreSQL. Umiej wyjasnic, dlaczego PostgreSQL jest zrodlem prawdy, dlaczego runner migracji jest lepszy od pojedynczych skryptow i jak ai_results przechowuje wynik oraz result_json.", None),
        ("Umiej wyjasnic pipeline: import FIT/CSV -> walidacja -> deduplikacja -> merge po czasie -> feature engineering -> wellness status -> raport PDF/trendy. Podkresl ryzyka QA: zle timestampy, brak danych, duplikaty, rozna czestotliwosc probkowania, artefakty HRV, rozjazd HR/pulse i jakosc danych.", None),
        ("Brakujace elementy, o ktorych trzeba mowic uczciwie", "Heading2"),
        ("Na rozmowie nie przedstawiaj systemu jako gotowego produktu medycznego. Poprawna narracja: to mocny wellness/research MVP i praktyczny projekt QA Automation, ktory pokazuje architekture, testowalnosc, dane, API i podejscie seniorowe. Produkt kliniczny wymagalby walidacji klinicznej, dokumentacji regulacyjnej, procesu QMS, risk management i formalnej zgodnosci.", None),
    ]
    append_section(path, marker, entries)


def update_technical() -> None:
    path = DOC_DIR / "Przygotowanie_do_rozmowy_technicznej_QA_Automation_FINAL.docx"
    marker = "AKTUALIZACJA 2026-07-24 - CORELABTECH TECHNICAL INTERVIEW UPDATE"
    entries = [
        (marker, "Heading1"),
        ("Jak polaczyc ten plik z WIEDZA_PROJEKT_QA_SCALONE_FINAL", "Heading2"),
        ("Ten dokument jest skryptem treningowym do rozmowy technicznej. Do szczegolow projektu, architektury i tabel wracaj do WIEDZA_PROJEKT_QA_SCALONE_FINAL, ale na rozmowie odpowiadaj krotko: decyzja, powod, trade-off, przyklad z CoreLabTech.", None),
        ("Aktualny opis projektu - EN", "Heading2"),
        ("CoreLabTech is a session-based wellness data analysis application. It uses Python, Flask and PostgreSQL, supports FIT/CSV imports, merges time-series measurements, calculates physiological features and stores AI-style wellness results in ai_results. The current direction is wellness and research support, not medical diagnosis. The most important QA risks are data quality, timestamp alignment, duplicate imports, authorization, API contract stability and report correctness.", None),
        ("Aktualny opis projektu - PL", "Heading2"),
        ("CoreLabTech to aplikacja do analizy danych sesyjnych wellness. Backend jest w Pythonie i Flasku, baza w PostgreSQL, a system obsluguje import FIT/CSV, laczenie pomiarow w czasie, wyliczanie cech i zapis wynikow wellness w ai_results. Kierunek produktu to wellness/research, nie diagnoza medyczna. Najwazniejsze ryzyka QA to jakosc danych, synchronizacja czasu, duplikaty importow, autoryzacja, stabilnosc kontraktow API i poprawnosc raportow.", None),
        ("Co zostalo zrobione ostatnio", "Heading2"),
        ("Dodano jednolity runner migracji ze schema_migrations, nowe migracje 011-012, struktury pod HRV i baseline: hrv_imports, hrv_intervals, session_features i daily_baselines. Uzupelniono moduly trend_analysis, longitudinal_analysis i adaptation_analysis. Raport PDF zostal przepiety na PostgreSQL i ai_results oraz przestawiony na jezyk wellness.", None),
        ("Pytanie: How would you test CoreLabTech?", "Heading2"),
        ("EN: I would test it on several layers. First, API tests for upload, merge, analysis and report endpoints, including negative cases and authorization. Second, database checks to verify that imports, merge jobs, merged measurements and ai_results are stored consistently. Third, data-quality tests with missing values, duplicated rows, timestamp drift and sensor mismatch. Finally, UI or Playwright smoke tests for the main user workflow: create a session, import data, run analysis, review trends and download a PDF report.", None),
        ("PL: Testowalbym to warstwowo: API dla uploadu, merge, analizy i raportu; walidacje bazy danych; przypadki jak brak danych, duplikaty, przesuniecia czasu i rozjazd sensorow; oraz smoke testy UI w Playwright dla glownego przeplywu uzytkownika.", None),
        ("Live coding - zadania, ktore warto przecwiczyc", "Heading2"),
        ("1. Remove duplicates while preserving order: uzyj set do sprawdzania seen i listy wynikowej do zachowania kolejnosci.", None),
        ("2. Merge two time-series lists by nearest timestamp: posortuj dane, przejdz wskaznikami albo zastosuj okno tolerancji, zwroc sparowane rekordy i oznacz brak dopasowania.", None),
        ("3. Validate an API response: sprawdz status code, wymagane pola, typy danych, wartosci graniczne i komunikaty bledow.", None),
        ("4. SQL baseline task: policz sredni RMSSD z ostatnich 7, 14 i 30 dni dla user_id oraz porownaj ostatnia sesje z baseline.", None),
        ("5. Test design task: zaprojektuj przypadki dla importu HRV/CSV/FIT, uwzgledniajac duplikaty, puste pliki, zly format, rozne timezone, brak synchronizacji i niski data_quality_score.", None),
        ("Senior answer pattern", "Heading2"),
        ("Odpowiadaj schematem: decyzja -> powod -> ryzyko/trade-off -> przyklad z CoreLabTech -> jak bym to testowal. Ten schemat pokazuje seniorowe myslenie i pomaga nie wpadac w zbyt dlugie definicje.", None),
    ]
    append_section(path, marker, entries)

    live_marker = "LIVE CODING JAVA / PYTHON / SQL - MODEL ANSWERS"
    live_entries = [
        (live_marker, "Heading1"),
        ("Jak odpowiadac podczas live coding", "Heading2"),
        ("Nie zaczynaj od pisania kodu bez komentarza. Najpierw powiedz: I will clarify the input and output, then I will cover edge cases, then I will implement a simple readable solution, and finally I will mention complexity. To pokazuje seniorowe myslenie nawet przy prostym zadaniu.", None),
        ("Schemat odpowiedzi: 1. doprecyzuj wymagania, 2. nazwij edge case'y, 3. napisz czytelne rozwiazanie, 4. podaj zlozonosc czasowa i pamieciowa, 5. zaproponuj testy.", None),
        ("Python task 1 - count word frequency", "Heading2"),
        ("Task: Given a text, count how many times each word appears. Ignore case and basic punctuation.", None),
        ("Python solution:", None),
        ("import re\nfrom collections import Counter\n\ndef count_words(text: str) -> dict[str, int]:\n    words = re.findall(r\"[a-zA-Z0-9]+\", text.lower())\n    return dict(Counter(words))\n\nprint(count_words(\"API test, api automation test\"))\n# {'api': 2, 'test': 2, 'automation': 1}", None),
        ("What to say: I normalize the text to lowercase, extract words with a regex and use Counter because it is readable and efficient. Complexity is O(n), where n is the number of words or characters processed.", None),
        ("Edge cases: empty string, punctuation only, mixed case, repeated spaces, numbers, non-English characters if required by the product.", None),
        ("Python task 2 - remove duplicates while preserving order", "Heading2"),
        ("Task: Return unique values from a list, preserving the first occurrence order.", None),
        ("Python solution:", None),
        ("def unique_preserve_order(items: list[str]) -> list[str]:\n    seen = set()\n    result = []\n    for item in items:\n        if item not in seen:\n            seen.add(item)\n            result.append(item)\n    return result\n\nprint(unique_preserve_order([\"fit\", \"csv\", \"fit\", \"hrv\"]))\n# ['fit', 'csv', 'hrv']", None),
        ("What to say: A set gives fast membership checks, while the result list preserves order. Complexity is O(n) time and O(n) memory.", None),
        ("Follow-up: If items are dictionaries, I need a stable key, for example file_hash, session_id or timestamp, because dictionaries are not hashable by default.", None),
        ("Python task 3 - validate API response", "Heading2"),
        ("Task: Validate that an API response contains required fields and correct types.", None),
        ("Python solution:", None),
        ("def validate_analysis_response(payload: dict) -> list[str]:\n    errors = []\n    required = {\n        \"status\": str,\n        \"session_id\": str,\n        \"wellness_status\": str,\n        \"data_quality_score\": (int, float),\n    }\n    for field, expected_type in required.items():\n        if field not in payload:\n            errors.append(f\"missing field: {field}\")\n        elif not isinstance(payload[field], expected_type):\n            errors.append(f\"invalid type for {field}\")\n    if payload.get(\"wellness_status\") not in {\n        \"baseline\", \"elevated_load\", \"recovery_trend\", \"data_quality_warning\"\n    }:\n        errors.append(\"invalid wellness_status\")\n    return errors", None),
        ("What to say: I validate contract, types and allowed values. In real automation I would put this into reusable API validators and use it in positive and negative API tests.", None),
        ("Python task 4 - merge two time-series by nearest timestamp", "Heading2"),
        ("Task: Match FIT and CSV records by timestamp if the difference is within a tolerance window.", None),
        ("Python solution:", None),
        ("from datetime import datetime, timedelta\n\ndef merge_by_nearest_time(fit_rows, csv_rows, tolerance_seconds=5):\n    csv_rows = sorted(csv_rows, key=lambda row: row[\"timestamp\"])\n    result = []\n    j = 0\n    tolerance = timedelta(seconds=tolerance_seconds)\n    for fit in sorted(fit_rows, key=lambda row: row[\"timestamp\"]):\n        best = None\n        while j < len(csv_rows) and csv_rows[j][\"timestamp\"] < fit[\"timestamp\"] - tolerance:\n            j += 1\n        for candidate in csv_rows[j:j + 3]:\n            delta = abs(candidate[\"timestamp\"] - fit[\"timestamp\"])\n            if delta <= tolerance and (best is None or delta < best[0]):\n                best = (delta, candidate)\n        result.append({\"fit\": fit, \"csv\": best[1] if best else None})\n    return result", None),
        ("What to say: I sort both streams and use a tolerance window. In production I would add timezone normalization, duplicate handling and data-quality flags for unmatched rows.", None),
        ("Java task 1 - count elements with HashMap", "Heading2"),
        ("Task: Count occurrences of strings in a list.", None),
        ("Java solution:", None),
        ("import java.util.*;\n\npublic static Map<String, Integer> countValues(List<String> values) {\n    Map<String, Integer> counts = new HashMap<>();\n    for (String value : values) {\n        counts.put(value, counts.getOrDefault(value, 0) + 1);\n    }\n    return counts;\n}", None),
        ("What to say: HashMap is appropriate because lookup and update are average O(1). I would also clarify whether counting should be case-sensitive.", None),
        ("Java task 2 - remove duplicates while preserving order", "Heading2"),
        ("Task: Remove duplicates but keep first occurrence order.", None),
        ("Java solution:", None),
        ("import java.util.*;\n\npublic static List<String> uniquePreserveOrder(List<String> values) {\n    return new ArrayList<>(new LinkedHashSet<>(values));\n}", None),
        ("What to say: LinkedHashSet combines uniqueness with insertion order. Complexity is O(n) time and O(n) memory.", None),
        ("Java task 3 - filter with Stream API", "Heading2"),
        ("Task: Return active users with role QA.", None),
        ("Java solution:", None),
        ("List<User> qaUsers = users.stream()\n    .filter(User::isActive)\n    .filter(user -> \"QA\".equals(user.getRole()))\n    .toList();", None),
        ("What to say: Streams are readable for transformations and filtering. For complex business logic I would extract predicates or use clear loops if readability is better.", None),
        ("Java task 4 - equals and hashCode follow-up", "Heading2"),
        ("Typical question: Why do equals and hashCode matter in tests or automation frameworks?", None),
        ("Model answer: They matter when objects are used in HashSet, HashMap or assertions comparing collections. If equals and hashCode are inconsistent, duplicate detection, grouping and comparisons may produce incorrect results. In test automation this can break validation of API models or database records.", None),
        ("SQL task 1 - find duplicates", "Heading2"),
        ("Task: Find duplicated imports by session_id and file_hash.", None),
        ("SQL solution:", None),
        ("SELECT session_id, file_hash, COUNT(*) AS import_count\nFROM hrv_imports\nGROUP BY session_id, file_hash\nHAVING COUNT(*) > 1;", None),
        ("What to say: GROUP BY defines the business key for duplicates, HAVING filters aggregated groups. I would confirm which columns define uniqueness.", None),
        ("SQL task 2 - latest analysis per user", "Heading2"),
        ("Task: Return latest AI/wellness result for each user.", None),
        ("SQL solution:", None),
        ("SELECT *\nFROM (\n    SELECT\n        ai_results.*,\n        ROW_NUMBER() OVER (\n            PARTITION BY user_id\n            ORDER BY created_at DESC, ai_result_id DESC\n        ) AS rn\n    FROM ai_results\n) ranked\nWHERE rn = 1;", None),
        ("What to say: I use ROW_NUMBER as a window function because it is clear and handles ties with ai_result_id.", None),
        ("SQL task 3 - RMSSD baseline 7/14/30 days", "Heading2"),
        ("Task: Calculate rolling baseline for one user.", None),
        ("SQL solution:", None),
        ("SELECT\n    user_id,\n    AVG(rmssd_avg) FILTER (WHERE baseline_date >= CURRENT_DATE - INTERVAL '7 days') AS rmssd_7d,\n    AVG(rmssd_avg) FILTER (WHERE baseline_date >= CURRENT_DATE - INTERVAL '14 days') AS rmssd_14d,\n    AVG(rmssd_avg) FILTER (WHERE baseline_date >= CURRENT_DATE - INTERVAL '30 days') AS rmssd_30d\nFROM daily_baselines\nWHERE user_id = :user_id\nGROUP BY user_id;", None),
        ("What to say: FILTER lets me calculate several windows in one query. I would also check data completeness, because a 7-day baseline based on one day is weak.", None),
        ("SQL task 4 - compare latest session to baseline", "Heading2"),
        ("Task: Compare latest session RMSSD with 30-day baseline.", None),
        ("SQL solution:", None),
        ("WITH latest_session AS (\n    SELECT user_id, rmssd_avg, created_at\n    FROM session_features\n    WHERE user_id = :user_id\n    ORDER BY created_at DESC\n    LIMIT 1\n), baseline AS (\n    SELECT user_id, rmssd_30d\n    FROM daily_baselines\n    WHERE user_id = :user_id\n    ORDER BY baseline_date DESC\n    LIMIT 1\n)\nSELECT\n    latest_session.user_id,\n    latest_session.rmssd_avg,\n    baseline.rmssd_30d,\n    ROUND(((latest_session.rmssd_avg - baseline.rmssd_30d) / NULLIF(baseline.rmssd_30d, 0)) * 100, 2) AS rmssd_delta_percent\nFROM latest_session\nJOIN baseline USING (user_id);", None),
        ("What to say: I use NULLIF to avoid division by zero. In production I would also handle missing baseline and return a data_quality_warning.", None),
        ("SQL task 5 - JOIN vs UNION", "Heading2"),
        ("Typical question: What is the difference between JOIN and UNION?", None),
        ("Model answer: JOIN combines columns from related tables horizontally based on a condition. UNION combines compatible result sets vertically and removes duplicates unless UNION ALL is used. In CoreLabTech I would use JOIN to combine sessions with analyses, and UNION only when combining similar rows from multiple sources.", None),
        ("Mini checklist before interview", "Heading2"),
        ("Umiesz napisac: Python Counter, Python remove duplicates, Java HashMap count, Java LinkedHashSet unique, SQL GROUP BY/HAVING duplicates, SQL ROW_NUMBER latest record, SQL baseline 7/14/30. Umiesz do kazdego powiedziec complexity, edge cases i test cases.", None),
    ]
    append_section(path, live_marker, live_entries)


def update_english() -> None:
    path = DOC_DIR / "Przygotowanie_do_rozmowy_z_lektorka_angielski_FINAL.docx"
    marker = "UPDATE 2026-07-24 - NATURAL ENGLISH FOR CORELABTECH"
    entries = [
        (marker, "Heading1"),
        ("How to use this update", "Heading2"),
        ("This document is for speaking practice. Do not try to sound overly technical. Use clear, natural sentences and give one concrete example from CoreLabTech or your QA background.", None),
        ("Updated project answer - simple English", "Heading2"),
        ("CoreLabTech is my practical QA automation and data project. It is a web application built with Python, Flask, PostgreSQL and Docker. The application imports session data from files, checks the quality of the data, merges measurements and creates a wellness report. I use this project to practise API testing, database validation, Playwright, test strategy and clean architecture. It also helps me explain technical decisions in English.", None),
        ("Short version - 30 seconds", "Heading2"),
        ("I am currently improving my automation skills through a practical project called CoreLabTech. It is a Python and Flask application with PostgreSQL and Docker. From a QA perspective, it gives me realistic examples of API testing, data validation, file import, reporting and automation strategy.", None),
        ("Why this project is useful for your career", "Heading2"),
        ("It connects my long QA experience with modern automation tools. I can talk about manual testing, API testing and leadership, but also show that I am actively developing Python, Playwright, Docker and database testing skills.", None),
        ("STAR story - technical challenge", "Heading2"),
        ("Situation: In CoreLabTech, data can come from different sources, for example FIT and CSV files. These files may have different timestamps and sampling frequencies. Task: My goal was to make the data reliable enough for analysis and reporting. Action: I focused on validation, duplicate detection, synchronized merge logic, data-quality scoring and clear reporting. Result: The system became easier to test and explain, and I could define realistic QA scenarios for API, database and UI automation.", None),
        ("Useful phrases when you need time", "Heading2"),
        ("Let me think for a second. I would explain it in a simple way. To give you a concrete example from my project. The main challenge was data quality. The trade-off was between simplicity and flexibility. I would test it on API, database and UI levels.", None),
        ("Questions you can ask the interviewer or teacher", "Heading2"),
        ("Could you please correct my wording if it sounds unnatural? Could we practise follow-up questions about my latest project? Can we focus on fluency rather than perfect grammar for this answer? Could you challenge me with one technical question and one behavioural question?", None),
    ]
    append_section(path, marker, entries)


def main() -> None:
    update_scalone()
    update_technical()
    update_english()
    print("Updated interview preparation DOCX files.")


if __name__ == "__main__":
    main()
