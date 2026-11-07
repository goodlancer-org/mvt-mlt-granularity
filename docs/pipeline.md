> **Primary experiment update (2026-11-06).** Five variants (Standard, Aggregated-4/16, Dense-4/16), MVT and Rust MLT v1/v2, source-feature provenance and matched-block effect decomposition are now defined in [the extended experiment guide](extended_experiment.md). Run `python manage.py experiment`, then `python manage.py all`. Primary summaries live in `docs/data/extended/results.sqlite`; generated CSV/TeX files use `extended_` prefixes. The three-variant Python workflow and numerical claims below describe the historical study.

# Pipeline reference

The standalone workflows are documented in [conversion and preview](usage.md)
and [analysis](../analysis/README.md).

Stage A creates a canonical XY-only EPSG:3857 GeoPackage with spatial indexes,
physical bounds clipping and a normalization manifest. Stage B generates one MVT
MBTiles archive per variant with GDAL, repacks it to PMTiles and transcodes the
same tile payloads to MLT. MBTiles is a temporary container, not a measured
research output.

The analysis pipeline profiles raw/normalized sources, measures addresses and
unique payloads, audits decoded pairs, traces attribute types, materializes SQL
metrics and renders tables/figures. See the [data dictionary](data_dictionary.md)
for grain, units and NULL rules, and the [schema catalogue](schema.md) for columns.

[Release packaging](releasing.md) produces independent SQLite files and one
Parquet/CSV table bundle per database, with checksums and provenance.

## Codec version and retained archives

New conversions and repeat validation use `maplibre-tiles==0.4.1`. The existing
study archives and their compression measurements are retained; a validator
upgrade does not change their historical encoder provenance. The unmodified
0.4.1 decoder has a 64 MiB native budget per tile, independent of Docker RAM.

The project builds a source-verified binding patch exposing `max_memory_bytes`.
`MLT_DECODE_MEMORY_MIB` defaults to 256 and is passed explicitly to Rust Parser
and Decoder. Version, budget and patch provenance are recorded in audit metadata;
version and budget also invalidate the audit cache. This does not alter the encoder.
