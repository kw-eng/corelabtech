import json
import re
import unittest
from pathlib import Path

from services.i18n_service import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    TRANSLATIONS_DIRECTORY,
    catalog_for,
    translate,
    translations,
)


PLACEHOLDER_PATTERN = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")
MOJIBAKE_MARKERS = ("Ä", "Ĺ", "Ă", "Å")


def placeholders(value: str) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(value))


class I18nDictionaryTests(unittest.TestCase):
    def test_supported_locale_json_files_exist_and_parse(self):
        for locale in SUPPORTED_LOCALES:
            path = TRANSLATIONS_DIRECTORY / f"{locale}.json"

            self.assertTrue(path.exists(), f"Missing dictionary: {path}")
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            self.assertIsInstance(data, dict)
            self.assertGreater(len(data), 0)

    def test_all_locale_dictionaries_have_same_keys(self):
        catalogs = translations()
        base_keys = set(catalogs[DEFAULT_LOCALE])

        for locale in SUPPORTED_LOCALES:
            with self.subTest(locale=locale):
                locale_keys = set(catalogs[locale])
                self.assertEqual(
                    locale_keys,
                    base_keys,
                    (
                        f"{locale}.json keys differ from "
                        f"{DEFAULT_LOCALE}.json"
                    ),
                )

    def test_dictionary_values_are_non_empty_strings(self):
        for locale, catalog in translations().items():
            for key, value in catalog.items():
                with self.subTest(locale=locale, key=key):
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip())

    def test_placeholders_match_english_catalog(self):
        catalogs = translations()
        english = catalogs[DEFAULT_LOCALE]

        for locale, catalog in catalogs.items():
            for key, value in catalog.items():
                with self.subTest(locale=locale, key=key):
                    self.assertEqual(
                        placeholders(value),
                        placeholders(english[key]),
                    )

    def test_polish_dictionary_has_no_mojibake_markers(self):
        polish = translations()["pl"]

        for key, value in polish.items():
            with self.subTest(key=key):
                for marker in MOJIBAKE_MARKERS:
                    self.assertNotIn(marker, value)

    def test_catalog_for_merges_with_english_fallback(self):
        catalog = catalog_for("pl")

        self.assertEqual(catalog["nav.home"], "Start")
        self.assertIn("report.footer_notice", catalog)

    def test_chamber_operator_keys_are_translated(self):
        catalog = catalog_for("pl")

        self.assertEqual(catalog["chamber.hero_title"], "Sesja fizjologiczna")
        self.assertEqual(catalog["chamber.assign_package"], "Przypisz pakiet")
        self.assertNotEqual(
            catalog["chamber.client_profile"],
            "chamber.client_profile",
        )

    def test_translate_formats_chamber_progress(self):
        with self.subTest(locale=DEFAULT_LOCALE):
            self.assertEqual(
                translate("chamber.progress", progress=42),
                "Progress: 42%",
            )


if __name__ == "__main__":
    unittest.main()
