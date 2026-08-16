# Prompt 10.2 — Personal Baseline Foundation

Personal Baseline is an internal, evidence-governed backend foundation. It is deliberately not displayed in the dashboard or reports in Prompt 10.2.

## Kontekst (PL)

<details><summary>Dlaczego ta warstwa nie jest jeszcze widoczna dla klienta?</summary>

Warstwa definiuje wiarygodne dane referencyjne użytkownika przed wdrożeniem komunikatów o regeneracji lub postępie. Nie interpretuje norm populacyjnych ani nie stawia wniosków medycznych.

</details>

The implementation is versioned as `personal-baseline-v1`; the complete eligibility, provenance, quality, comparability, outlier and lineage contract is in [ADR_PERSONAL_BASELINE.md](architecture/ADR_PERSONAL_BASELINE.md). A Personal Baseline refresh is a derived materialization: if that write fails, the successful authoritative session analysis remains committed and the failure is logged for an operator retry.
