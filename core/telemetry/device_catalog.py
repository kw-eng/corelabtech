"""Conservative device capability catalog used during import.

Only explicitly named devices are classified as chest HRM/ECG. Unknown FIT
files remain wearable telemetry even when they contain heart-rate samples.
"""

from __future__ import annotations

from core.telemetry.contract import (
    METHOD_ECG,
    METHOD_PPG,
    METHOD_UNKNOWN,
    QUALITY_HIGH,
    QUALITY_MEDIUM,
    QUALITY_UNKNOWN,
    SOURCE_CHEST_HRM,
    SOURCE_WEARABLE_FIT,
    SOURCE_WATCH_PPG,
)


CHEST_HRM_MODELS = (
    "polar h10",
    "garmin hrm-pro",
    "garmin hrm pro",
    "garmin hrm-600",
    "garmin hrm 600",
    "garmin hrm-dual",
    "garmin hrm dual",
)

# Garmin product identifiers emitted in FIT device_info messages. The activity
# recorder can be a watch while an external HRM remains the source of RR.
GARMIN_CHEST_HRM_PRODUCTS = {
    4607: "Garmin HRM 600",
}

WATCH_PPG_MODELS = (
    "apple watch",
    "garmin fenix",
    "garmin forerunner",
    "polar vantage",
    "polar ignite",
    "samsung galaxy watch",
    "pixel watch",
)


DEVICE_COMPATIBILITY_VERSION = "device-compatibility-v1"

# This is a product-compatibility declaration, not a clinical validation list.
# ``conditional`` means that the resulting file or API payload must be reviewed
# by the importer before the signal is used for a particular analysis.
DEVICE_COMPATIBILITY_MATRIX = (
    {
        "id": "polar-h10", "manufacturer": "Polar", "model": "H10",
        "device_class": "chest_hrm_ecg", "manual_export": "conditional",
        "formats": ["CSV via Polar Flow", "FIT via Polar Flow"],
        "raw_rr": "conditional", "reported_hrv": "no", "timestamps": "yes",
        "official_api": "Polar AccessLink", "cloud_account": "conditional",
        "support_level": "core", "import_types": ["polar_csv", "fit"],
        "analysis_role": "raw_rr_when_present_and_verified",
        "verification_status": "conditional",
        "source_url": "https://support.polar.com/us-en/export-training-sessions-flow",
    },
    {
        "id": "garmin-hrm-600", "manufacturer": "Garmin", "model": "HRM 600",
        "device_class": "chest_hrm_ecg", "manual_export": "conditional",
        "formats": ["FIT via paired Garmin device/Connect"],
        "raw_rr": "conditional", "reported_hrv": "no", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "conditional",
        "support_level": "core", "import_types": ["fit"],
        "analysis_role": "raw_rr_when_present_and_verified",
        "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "garmin-hrm-pro-plus", "manufacturer": "Garmin", "model": "HRM-Pro Plus",
        "device_class": "chest_hrm_ecg", "manual_export": "conditional",
        "formats": ["FIT via paired Garmin device/Connect"],
        "raw_rr": "conditional", "reported_hrv": "no", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "conditional",
        "support_level": "core", "import_types": ["fit"],
        "analysis_role": "raw_rr_when_present_and_verified", "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "garmin-hrm-dual", "manufacturer": "Garmin", "model": "HRM-Dual",
        "device_class": "chest_hrm_ecg", "manual_export": "conditional",
        "formats": ["FIT via paired Garmin device/Connect"],
        "raw_rr": "conditional", "reported_hrv": "no", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "conditional",
        "support_level": "core", "import_types": ["fit"],
        "analysis_role": "raw_rr_when_present_and_verified", "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "checkme-o2", "manufacturer": "ViHealth/Checkme", "model": "Checkme O2",
        "device_class": "finger_oximeter_ppg", "manual_export": "yes",
        "formats": ["CSV"], "raw_rr": "no", "reported_hrv": "no", "timestamps": "yes",
        "official_api": "not_public", "cloud_account": "conditional",
        "support_level": "core", "import_types": ["csv"],
        "analysis_role": "spo2_reference_pulse_auxiliary", "verification_status": "verified",
        "source_url": "local-reference-export",
    },
    {
        "id": "garmin-fenix-8", "manufacturer": "Garmin", "model": "fenix 8",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV summary"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "required",
        "support_level": "trend", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "garmin-forerunner-965", "manufacturer": "Garmin", "model": "Forerunner 965",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV summary"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "required",
        "support_level": "trend", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "garmin-epix-pro", "manufacturer": "Garmin", "model": "epix Pro",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV summary"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "required",
        "support_level": "trend", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "garmin-venu-3", "manufacturer": "Garmin", "model": "Venu 3",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV summary"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Garmin Health API partner", "cloud_account": "required",
        "support_level": "trend", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.garmin.com/en-NZ/?faq=W1TvTPW8JZ6LfJSfK512Q8",
    },
    {
        "id": "polar-vantage-v3", "manufacturer": "Polar", "model": "Vantage V3",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Polar AccessLink", "cloud_account": "required",
        "support_level": "trend", "import_types": ["polar_csv", "fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.polar.com/us-en/export-training-sessions-flow",
    },
    {
        "id": "polar-ignite-3", "manufacturer": "Polar", "model": "Ignite 3",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Polar AccessLink", "cloud_account": "required",
        "support_level": "trend", "import_types": ["polar_csv", "fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.polar.com/us-en/export-training-sessions-flow",
    },
    {
        "id": "polar-pacer-pro", "manufacturer": "Polar", "model": "Pacer Pro",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["FIT", "TCX", "GPX", "CSV"],
        "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Polar AccessLink", "cloud_account": "required",
        "support_level": "trend", "import_types": ["polar_csv", "fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.polar.com/us-en/export-training-sessions-flow",
    },
    {
        "id": "apple-watch-series", "manufacturer": "Apple", "model": "Apple Watch Series",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["Apple Health export.xml"], "raw_rr": "no", "reported_hrv": "yes", "timestamps": "yes",
        "official_api": "HealthKit", "cloud_account": "conditional",
        "support_level": "trend", "import_types": ["apple_health_xml"],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://support.apple.com/en-us/108806",
    },
    {
        "id": "apple-watch-ultra", "manufacturer": "Apple", "model": "Apple Watch Ultra",
        "device_class": "watch_ppg", "manual_export": "yes",
        "formats": ["Apple Health export.xml"], "raw_rr": "no", "reported_hrv": "yes", "timestamps": "yes",
        "official_api": "HealthKit", "cloud_account": "conditional",
        "support_level": "trend", "import_types": ["apple_health_xml"],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://support.apple.com/en-us/108806",
    },
    {
        "id": "samsung-galaxy-watch", "manufacturer": "Samsung", "model": "Galaxy Watch",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["Health Connect JSON bridge"], "raw_rr": "no", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Health Connect", "cloud_account": "conditional",
        "support_level": "trend", "import_types": ["health_connect_json"],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://developer.android.com/health-and-fitness/guides/health-connect",
    },
    {
        "id": "google-pixel-watch", "manufacturer": "Google", "model": "Pixel Watch",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["Health Connect JSON bridge"], "raw_rr": "no", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Health Connect", "cloud_account": "conditional",
        "support_level": "trend", "import_types": ["health_connect_json"],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://developer.android.com/health-and-fitness/guides/health-connect",
    },
    {
        "id": "fitbit-sense-2", "manufacturer": "Fitbit", "model": "Sense 2",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["Fitbit account export"], "raw_rr": "no", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Fitbit Web API", "cloud_account": "required",
        "support_level": "planned", "import_types": [],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://dev.fitbit.com/build/reference/web-api/",
    },
    {
        "id": "fitbit-charge-6", "manufacturer": "Fitbit", "model": "Charge 6",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["Fitbit account export"], "raw_rr": "no", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "Fitbit Web API", "cloud_account": "required",
        "support_level": "planned", "import_types": [],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://dev.fitbit.com/build/reference/web-api/",
    },
    {
        "id": "oura-ring-gen3", "manufacturer": "Oura", "model": "Ring Gen3",
        "device_class": "ring_ppg", "manual_export": "conditional",
        "formats": ["Oura API JSON"], "raw_rr": "no", "reported_hrv": "yes", "timestamps": "yes",
        "official_api": "Oura API v2 OAuth", "cloud_account": "required",
        "support_level": "planned", "import_types": [],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://cloud.ouraring.com/v2/docs",
    },
    {
        "id": "oura-ring-4", "manufacturer": "Oura", "model": "Ring 4",
        "device_class": "ring_ppg", "manual_export": "conditional",
        "formats": ["Oura API JSON"], "raw_rr": "no", "reported_hrv": "yes", "timestamps": "yes",
        "official_api": "Oura API v2 OAuth", "cloud_account": "required",
        "support_level": "planned", "import_types": [],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://cloud.ouraring.com/v2/docs",
    },
    {
        "id": "whoop-5", "manufacturer": "WHOOP", "model": "WHOOP 5",
        "device_class": "strap_ppg", "manual_export": "conditional",
        "formats": ["WHOOP API JSON"], "raw_rr": "no", "reported_hrv": "yes", "timestamps": "yes",
        "official_api": "WHOOP API v2 OAuth", "cloud_account": "required",
        "support_level": "planned", "import_types": [],
        "analysis_role": "reported_hrv_and_trend_only", "verification_status": "conditional",
        "source_url": "https://developer.whoop.com/api/",
    },
    {
        "id": "suunto-race", "manufacturer": "Suunto", "model": "Race",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["FIT", "GPX via Suunto app"], "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "partner/conditional", "cloud_account": "required",
        "support_level": "planned", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://www.suunto.com/Support/",
    },
    {
        "id": "suunto-vertical", "manufacturer": "Suunto", "model": "Vertical",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["FIT", "GPX via Suunto app"], "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "partner/conditional", "cloud_account": "required",
        "support_level": "planned", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://www.suunto.com/Support/",
    },
    {
        "id": "coros-pace-3", "manufacturer": "COROS", "model": "PACE 3",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["FIT", "GPX"], "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "not_public", "cloud_account": "required",
        "support_level": "planned", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.coros.com/",
    },
    {
        "id": "coros-apex-2-pro", "manufacturer": "COROS", "model": "APEX 2 Pro",
        "device_class": "watch_ppg", "manual_export": "conditional",
        "formats": ["FIT", "GPX"], "raw_rr": "conditional", "reported_hrv": "conditional", "timestamps": "yes",
        "official_api": "not_public", "cloud_account": "required",
        "support_level": "planned", "import_types": ["fit"],
        "analysis_role": "watch_trend_unless_external_hrm_is_verified", "verification_status": "conditional",
        "source_url": "https://support.coros.com/",
    },
)


def resolve_fit_device(model: str | None) -> dict[str, str]:
    """Resolve known chest straps while keeping every other FIT source unknown."""

    normalized = (model or "").strip().lower()
    if any(known in normalized for known in CHEST_HRM_MODELS):
        return {
            "device_type": SOURCE_CHEST_HRM,
            "measurement_method": METHOD_ECG,
            "signal_quality": QUALITY_HIGH,
            "quality_reason": "known_chest_hrm_model",
        }

    return {
        "device_type": SOURCE_WEARABLE_FIT,
        "measurement_method": METHOD_UNKNOWN,
        "signal_quality": QUALITY_UNKNOWN,
        "quality_reason": "device_measurement_method_not_confirmed",
    }


def resolve_device_capability(model: str | None) -> dict[str, str]:
    """Resolve known device classes without promoting watch PPG to ECG."""

    chest = resolve_fit_device(model)
    if chest["device_type"] == SOURCE_CHEST_HRM:
        return chest

    normalized = (model or "").strip().lower()
    if any(known in normalized for known in WATCH_PPG_MODELS):
        return {
            "device_type": SOURCE_WATCH_PPG,
            "measurement_method": METHOD_PPG,
            "signal_quality": QUALITY_MEDIUM,
            "quality_reason": "watch_ppg_trend_only",
        }
    return chest


def device_catalog() -> list[dict[str, object]]:
    """Expose device classes plus per-model compatibility declarations."""

    classes = [
        {
            "device_class": "chest_hrm_ecg",
            "examples": "Polar H10, Garmin HRM 600, Garmin HRM-Pro, Garmin HRM-Dual",
            "measurement_method": METHOD_ECG,
            "signal_quality": QUALITY_HIGH,
            "hrv_policy": "raw_rr_eligible",
        },
        {
            "device_class": "finger_oximeter_ppg",
            "examples": "Checkme O2 and compatible pulse oximeters",
            "measurement_method": METHOD_PPG,
            "signal_quality": QUALITY_MEDIUM,
            "hrv_policy": "spo2_reference_pulse_auxiliary",
        },
        {
            "device_class": "watch_ppg",
            "examples": "Apple Watch, Garmin watches, Polar watches, Galaxy Watch, Pixel Watch",
            "measurement_method": METHOD_PPG,
            "signal_quality": QUALITY_MEDIUM,
            "hrv_policy": "trend_only_no_raw_rr_inference",
        },
        {
            "device_class": "unknown",
            "examples": "Unrecognized device or incomplete metadata",
            "measurement_method": METHOD_UNKNOWN,
            "signal_quality": QUALITY_UNKNOWN,
            "hrv_policy": "not_eligible_until_verified",
        },
    ]
    return classes


def device_compatibility_matrix() -> list[dict[str, object]]:
    """Return copies so callers cannot mutate the declared compatibility data."""

    return [dict(device) for device in DEVICE_COMPATIBILITY_MATRIX]


def resolve_garmin_product(product_id: object) -> str | None:
    """Return a verified chest-HRM model for a FIT product identifier."""

    try:
        return GARMIN_CHEST_HRM_PRODUCTS.get(int(product_id))
    except (TypeError, ValueError):
        return None
