# Measured experiment data

The primary extended study uses `extended/` (Parquet observations and
`extended/results.sqlite`) and `extended_*.csv` / `extended_claims.json` /
`extended_checks.md`. Run `python manage.py experiment`, then `python manage.py all`.
See [the experiment guide](../extended_experiment.md) for the schema, exact Rust
build, source-feature provenance, normalization qualifications and reproduction.

`source_stats.sqlite` and `normalized_stats.sqlite` inventory the unchanged source
and normalized files. Report generation verifies their input hashes before reuse.

Unprefixed three-variant CSVs, `tile_stats/` and the original `results.sqlite` are
historical exports, retained for compatibility and snapshotted under
`historical/python-0.2.2/`. They are not mixed into primary extended comparisons.
The 0.4.1 repeat audit of those historical archives is documented separately in
`../validation/mlt-0.4.1.md`.

Large generated data are excluded from the software Git repository. Dataset export
packages the primary Parquet tables, SQLite summaries, unrounded report inputs,
source-ID lookups, conversion provenance and checksums. The earlier published
dataset DOI remains a historical release until an expanded release is published.
