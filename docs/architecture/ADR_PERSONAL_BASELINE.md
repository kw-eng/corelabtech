# ADR: Evidence-governed Personal Baseline

## Status

Accepted for Prompt 10.2 as `personal-baseline-v1`.

## Purpose and boundary

Personal Baseline is a user's own historical reference for a metric. It is not a population norm, medical reference, Wellness Score, data-quality score, confidence, Recovery, Progress, Readiness, or Performance score. It does not make causal claims about HBOT or any intervention.

## Eligible metrics and provenance

| Metric | Unit | Required provenance |
| --- | --- | --- |
| `hrv_rmssd`, `hrv_sdnn` | ms | Approved `chest_hrm_ecg_only-v1` RR provenance, 20+ accepted RR intervals, medium/high HRV confidence |
| `reference_heart_rate` | bpm | During-session chest HRM ECG value only; PPG pulse and snapshots are excluded |
| `spo2_during_session` | % | During-session synchronized approved pulse-oximeter source, >=80% signal and temporal coverage, medium/high alignment |

Duration, ATA, oxygen flow, and temperature are contextual comparability fields, not physiological baseline metrics in v1.

## Eligibility and comparability

All observations are user-scoped, dated in a deterministic rolling 30-day inclusive window, `during` phase only, exact protocol scoped, and target ATA-compatible within 0.05 ATA when both values exist. The data-quality gate is `>=70`. Check-in and recovery snapshots are excluded; no pulse-to-HR or snapshot-to-PRE/POST conversion is permitted.

## Minimum evidence, calculation and outliers

At least 3 eligible observations are required. Fewer observations return `insufficient_evidence`, not a numerical baseline. Available baselines use the median, with observed eligible minimum/maximum bounds. At 5+ eligible observations, a metric-specific modified MAD z-score may exclude only values with absolute score greater than 3.5. Borderline values are retained; zero MAD disables statistical exclusion. Exclusions remain in lineage as `outlier_excluded`.

## Lineage, versioning and recalculation

Every materialization records policy version, calculation timestamp, eligible session references, rejected references/reasons, counts, scope and policy settings. `personal-baseline-v1` is never silently reinterpreted: a policy change requires a new version. Calculations run after successful session analysis and are persisted additively in `personal_baselines`; legacy `daily_baselines` remain untouched rolling aggregates.

## Rejection reasons

`snapshot_excluded`, `incompatible_protocol`, `insufficient_quality`, `unsupported_provenance`, `insufficient_coverage`, `missing_metric`, `invalid_value`, and `outlier_excluded` are stable internal identifiers. Customer-facing localization is deferred because this backend foundation introduces no customer baseline UI or PDF content.

## Security, privacy and presentation

Queries are user-scoped and no endpoint is introduced. Internal lineage retains secure session identifiers for audit; a future customer projection must use safe date/session references rather than raw IDs. No raw telemetry, storage paths, secrets or stack traces are recorded.

## Alternatives considered

Reusing `daily_baselines` was rejected because it mixes rolling aggregates without metric eligibility, provenance, outlier, policy-version or rejection lineage semantics. Computing only on demand was rejected because reproducibility and audit lineage need a durable materialization. A population/reference-range approach was rejected because it is outside the product and safety boundary.

## Future integration

Recovery and Progress may consume an available Personal Baseline only after their own evidence contracts and localized customer projections are approved. They must not change the v1 baseline meaning.
