# RepoLens Changelog

One entry per shipped commit/sprint, newest first.

## Sprint 2 — Security engine hardening
- Central redaction + rule-failure reporting in the registry (ADR-026).
- Logical-line scanning for multi-line calls (ADR-027).
- SEC-010: function name no longer counts as auth evidence; auth markers tightened.
- Pattern-based rules relabelled `STATIC_RULE`; Node cookie pattern fixed.
- Crashed rules are counted in the audit summary (`security_rule_errors`).
- 54 new tests: positive/negative fixtures for every rule.

## Sprint 1 — Audit foundation
- `file_contents` table; ingestion persists original source (ADR-023).
- `symbols.metadata_json`; Python parser extracts `route` / `http_method` (ADR-024).
- Audit worker analyses original source, re-parses for real call references, batches DB reads, groups symbols once.
- Tests: route extraction, persistence, exact line numbers, no duplicates, reachability, SEC-010, missing-source failure.

## Sprint 0 — Baseline
- CI workflow (pytest on push/PR).
- CORS: explicit allow-list via `CORS_ORIGINS` (ADR-025) + regression test.