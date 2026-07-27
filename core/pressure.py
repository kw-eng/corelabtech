"""Pressure-unit conversion shared by wellness session workflows."""

STANDARD_ATMOSPHERE_KPA = 101.325


def calculate_pressure_ata(
    pressure_value: float,
    pressure_unit: str,
) -> float:
    """Convert supported pressure representations into absolute atmospheres."""

    value = float(pressure_value)

    if pressure_unit == "ata":
        return value
    if pressure_unit == "kpa_absolute":
        return value / STANDARD_ATMOSPHERE_KPA
    if pressure_unit == "kpa_gauge":
        return 1.0 + (value / STANDARD_ATMOSPHERE_KPA)

    raise ValueError("invalid pressure_input_unit")
