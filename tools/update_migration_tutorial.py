from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W_NS)

DOCX_PATH = Path(
    r"D:\corelabtech_tutorials\wiedza_QA_WEB"
    r"\Tutorial_Migracja_CoreLabTech_SQLite_PostgreSQL.docx"
)


def qn(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(t.text or "" for t in paragraph.iter(qn("t"))).strip()


def set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    runs = list(paragraph.findall(qn("r")))
    for run in runs:
        paragraph.remove(run)

    run = ET.SubElement(paragraph, qn("r"))
    node = ET.SubElement(run, qn("t"))
    node.text = text


def new_paragraph(text: str) -> ET.Element:
    paragraph = ET.Element(qn("p"))
    run = ET.SubElement(paragraph, qn("r"))
    node = ET.SubElement(run, qn("t"))
    node.text = text
    return paragraph


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)

        with zipfile.ZipFile(DOCX_PATH, "r") as zin:
            zin.extractall(temp)

        document_xml = temp / "word" / "document.xml"
        tree = ET.parse(document_xml)
        root = tree.getroot()
        body = root.find(qn("body"))
        if body is None:
            raise RuntimeError("DOCX has no document body")

        replacements = {
            "Ten dokument opisuje aktualny, poprawny merytorycznie stan migracji CoreLabTech z dawnego prototypu SQLite do PostgreSQL. Nie jest to juz tylko instrukcja instalacji bazy w pgAdmin. To tutorial pokazujacy aktualna architekture aplikacji, migracje 004-010, import FIT/CSV, merge, AI analysis, Docker, security i QA.": "Ten dokument opisuje aktualny, poprawny merytorycznie stan migracji CoreLabTech z dawnego prototypu SQLite do PostgreSQL. Nie jest to juz tylko instrukcja instalacji bazy w pgAdmin. To tutorial pokazujacy aktualna architekture aplikacji, jednolity runner migracji, migracje 004-012, import FIT/CSV/HRV, merge, wellness analysis, Docker, security i QA.",
            "4. Aktualne migracje 004-010": "4. Aktualne migracje 004-012",
            "Brakuje jeszcze pelnego testu na realnym pliku Fenix 8 z wlaczonym Log HRV oraz osobnych tabel hrv_imports/hrv_intervals, jezeli RR ma byc przechowywane jako pelnoprawne zrodlo historyczne.": "Pelny test na realnym pliku Fenix 8 z wlaczonym Log HRV nadal jest potrzebny, ale struktury pod HRV sa juz przygotowane: hrv_imports i hrv_intervals przechowuja importy oraz interwaly RR jako pelnoprawne zrodlo historyczne.",
            "services/analysis_service.py jest deterministycznym silnikiem rule-based, a nie klinicznym modelem medycznym.": "services/analysis_service.py jest deterministycznym silnikiem rule-based w trybie wellness/research, a nie klinicznym modelem medycznym.",
            "Liczy m.in. match_rate, avg/min/max SpO2, HR, pulse, HRV, roznice HR-pulse, hypoxia/stress/cardiovascular warnings, data_quality_score i summary.": "Liczy m.in. match_rate, avg/min/max SpO2, HR, pulse, HRV, roznice HR-pulse, data_quality_score, wellness_status, elevated_load, oxygenation_drop, sensor_alignment_warning i summary. Starsze kolumny ai_results pozostaja dla kompatybilnosci, ale raport i API powinny uzywac jezyka wellness.",
            "5. Uruchom migracje 004-010, jezeli baza jest nowa.": "5. Uruchom python run_database_setup.py, jezeli baza jest nowa albo wymaga aktualizacji migracji 004-012.",
        }

        paragraphs = list(body.findall(qn("p")))
        for paragraph in paragraphs:
            text = paragraph_text(paragraph)
            if text in replacements:
                set_paragraph_text(paragraph, replacements[text])

        paragraphs = list(body.findall(qn("p")))
        for index, paragraph in enumerate(paragraphs):
            if paragraph_text(paragraph) == (
                "tworzy ai_results z score, flags, summary, recommendations, "
                "features_json i result_json."
            ):
                body.insert(index + 1, new_paragraph("011_create_hrv_tables.py"))
                body.insert(
                    index + 2,
                    new_paragraph(
                        "tworzy hrv_imports i hrv_intervals dla importow HRV/RR, "
                        "metadanych zrodel, file_hash, statusow, interwalow RR, "
                        "quality_flag oraz indeksow po session_id, user_id i timestamp."
                    ),
                )
                body.insert(index + 3, new_paragraph("012_create_session_features_baselines.py"))
                body.insert(
                    index + 4,
                    new_paragraph(
                        "tworzy session_features i daily_baselines, czyli warstwe pod "
                        "PRE/DURING/POST, baseline RMSSD 7/14/30 dni, resting HR, "
                        "SpO2 average/minimum, data_quality i status wellness."
                    ),
                )
                break

        old_todo = {
            "Utworzyc jednolity runner migracji zamiast uruchamiania pojedynczych skryptow.",
            "Przeniesc stare elementy SQLite do archiwum albo usunac po potwierdzeniu, ze PostgreSQL jest jedynym zrodlem prawdy.",
            "Wydzielic subjects_routes.py i admin_routes.py z bardzo duzego research_routes.py.",
            "Dodac hrv_imports, hrv_intervals, session_features i daily_baselines.",
            "Wypelnic core/analytics/trend_analysis.py, longitudinal_analysis.py i adaptation_analysis.py.",
            "Przepiac raport PDF w pelni na PostgreSQL i ai_results.",
        }

        paragraphs = list(body.findall(qn("p")))
        heading_index = None
        for index, paragraph in enumerate(paragraphs):
            if paragraph_text(paragraph) == "14. Co jest nadal do poprawy":
                heading_index = list(body).index(paragraph)
                break

        if heading_index is None:
            raise RuntimeError("Could not find section 14")

        for child in list(body)[heading_index + 1 :]:
            if child.tag == qn("sectPr"):
                break
            if paragraph_text(child) in old_todo:
                body.remove(child)

        updated_section = [
            "✅ Zrobione po ostatnich poprawkach",
            "✅ Jednolity runner migracji run_database_setup.py obsluguje schema_migrations, checksum i pomija migracje juz wykonane.",
            "✅ Migracje 011 i 012 zostaly dodane do runnera.",
            "✅ Dodano struktury hrv_imports i hrv_intervals pod import HRV/RR z Garmin/Elite/FIT.",
            "✅ Dodano session_features i daily_baselines pod PRE/DURING/POST, baseline RMSSD 7/14/30, resting HR, SpO2 i status wellness.",
            "✅ Uzupelniono core/analytics/trend_analysis.py, longitudinal_analysis.py i adaptation_analysis.py podstawowymi funkcjami trendu, baseline i recovery status.",
            "✅ Raport PDF korzysta z PostgreSQL i ai_results oraz pokazuje jezyk wellness: wellness score, load score, oxygenation minimum, heart-rate peak, data quality i session flagged.",
            "✅ analysis_service.py zwraca wellness aliases: product_mode, wellness_status, session_flagged, elevated_load, oxygenation_drop, sensor_alignment_warning i wellness_flags.",
            "✅ Endpoint trendow uzytkownika zwraca dodatkowe pola wellness: session_flagged, wellness_status, elevated_load, oxygenation_drop, sensor_alignment_warning i flagged_session_count.",
            "🟡 Nadal do poprawy przed mocnym wellness MVP",
            "🟡 Uruchomic migracje 004-012 na docelowej bazie PostgreSQL w pelnym srodowisku z zainstalowanym psycopg2-binary.",
            "🟡 Przetestowac parser FIT/HRV na realnym pliku Garmin Fenix 8 z wlaczonym Log HRV oraz na danych HRM600/Elite, jezeli beda uzywane jako drugie zrodlo.",
            "🟡 Dodac testy integracyjne dla hrv_imports, hrv_intervals, session_features i daily_baselines.",
            "🟡 Dodac automatyczne wyliczanie daily_baselines z danych historycznych, a nie tylko strukture tabel.",
            "🟡 Doprecyzowac data-quality rules: minimalna liczba probek RR, artifact ratio, brakujace timestampy, timezone, duplikaty i rozjazd HR/pulse.",
            "🟡 Dodac testy raportu PDF: czy raport powstaje, czy czyta ai_results, czy uzywa jezyka wellness i czy nie sugeruje diagnozy medycznej.",
            "🟡 Zaktualizowac README/runbook o nowa kolejnosc: Docker -> run_database_setup.py -> seed/admin -> import -> merge -> analysis -> report.",
            "⬜ Wieksze prace, ktore zostaja na pozniej",
            "⬜ Wydzielic subjects_routes.py i admin_routes.py z bardzo duzego research_routes.py.",
            "⬜ Przeniesc stare elementy SQLite do archiwum albo usunac po finalnym potwierdzeniu, ze PostgreSQL jest jedynym zrodlem prawdy.",
            "⬜ Zrobic pelny importer Elite HRV/CSV, jezeli Garmin FIT z Log HRV nie da wystarczajaco dobrych danych.",
            "⬜ Zbudowac aplikacje mobilna CoreLabTech Mobile: tworzenie sesji, import FIT/CSV/Elite HRV, merge, raport PRE/DURING/POST, trendy i eksport PDF.",
            "⬜ Dla sprzedazy klinicznej przygotowac osobny tor: QMS, risk management, walidacje, dokumentacje regulacyjna i jasne oddzielenie od trybu wellness.",
        ]

        insertion_index = heading_index + 1
        for offset, text in enumerate(updated_section):
            body.insert(insertion_index + offset, new_paragraph(text))

        tree.write(document_xml, encoding="utf-8", xml_declaration=True)

        with zipfile.ZipFile(DOCX_PATH, "w", zipfile.ZIP_DEFLATED) as zout:
            for file_path in temp.rglob("*"):
                if file_path.is_file():
                    zout.write(file_path, file_path.relative_to(temp).as_posix())

    print(f"Updated {DOCX_PATH}")


if __name__ == "__main__":
    main()
