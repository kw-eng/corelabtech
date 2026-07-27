import unittest

from core.pressure import calculate_pressure_ata


class PressureConversionTests(unittest.TestCase):
    def test_gauge_kpa_to_ata(self):
        self.assertAlmostEqual(
            calculate_pressure_ata(50.6625, "kpa_gauge"),
            1.5,
            places=6,
        )

    def test_absolute_kpa_to_ata(self):
        self.assertAlmostEqual(
            calculate_pressure_ata(151.9875, "kpa_absolute"),
            1.5,
            places=6,
        )

    def test_direct_ata_is_preserved(self):
        self.assertEqual(
            calculate_pressure_ata(1.3, "ata"),
            1.3,
        )

    def test_unknown_unit_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_pressure_ata(50, "psi")


if __name__ == "__main__":
    unittest.main()
