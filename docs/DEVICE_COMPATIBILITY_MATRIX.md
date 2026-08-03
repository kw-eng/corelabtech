# Device Compatibility Matrix

CoreLabTech exposes the versioned `device-compatibility-v1` matrix through
`GET /api/device-catalog`. The application source is
`core/telemetry/device_catalog.py`; this document defines how to use it.

## Purpose

The matrix is product documentation, not a clinical validation registry. It
helps an operator choose an import path and tells a user what the platform can
actually analyse from that source.

Each device record declares manual export formats, timestamp availability,
raw RR availability, manufacturer-reported HRV, official API route, cloud
requirement, CoreLabTech support level and a manufacturer/source link.

## Support levels

| Level | Meaning |
| --- | --- |
| `core` | Supported in the recommended session workflow. |
| `trend` | A supported import can provide trends or manufacturer-reported HRV. |
| `planned` | Listed for transparent roadmap planning; no import route exists yet. |

## Data policy

`raw_rr=yes` or `conditional` never permits HRV automatically. The imported
payload must contain valid RR intervals and pass source and artifact checks.

`reported_hrv=yes` is retained as a manufacturer metric. It does not replace
raw RR and is not used to calculate RMSSD, SDNN or pNN50.

The `verification_status` field has three values:

| Status | Meaning |
| --- | --- |
| `verified` | Reference export or official data route has been checked by the project. |
| `conditional` | The route exists, but the exact payload varies by configuration, account or paired sensor. |
| `unsupported` | No safe import path is currently declared. |

## Change control

Any new device requires an anonymized reference export, importer test fixture
and review of timestamp, RR unit and measurement provenance before changing a
record to `verified`.

## Reference-export test set

`tests/api/test_telemetry_reference_exports.py` is the regression gate for
every registered importer. It keeps two kinds of non-production input:

| Kind | Files | What it proves |
| --- | --- | --- |
| `anonymized_reference_export` | Garmin HRM 600 FIT, Garmin fenix 8 FIT, Checkme O2 CSV | The current parser accepts a real, anonymized project export and preserves the declared signals. |
| `schema_fixture` | Polar CSV, Apple Health XML, Health Connect JSON | The documented adapter contract remains stable; it is not evidence that every account or device configuration has been verified. |

Only the Checkme O2 entry is currently marked `verified`: it has an
anonymized export and an importer path whose SpO2/pulse semantics are covered
by the reference test. Garmin HRM 600 and fēnix 8 exports are regression
coverage for the FIT parser, but their device classification remains
`conditional` until the source device and paired-sensor metadata are reviewed
for each exported session. Apple Health, Polar and Health Connect remain
`conditional` until an anonymized export from the respective production path
is added to the test set.
