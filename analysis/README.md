# Reproduce the measurements

Run commands from this repository after `python manage.py env`. The corpus registry
is [`datasets.json`](datasets.json); source checksums are in [`sources.json`](sources.json).
Recover the matching raw files, normalize them and generate all three paired
variants before running the complete analysis. [Source availability](../docs/sources.md).

```sh
python manage.py analyze sources
python manage.py analyze normalized
python manage.py analyze tiles
python manage.py audit
python manage.py types
python manage.py stats
python manage.py report
# All seven stages, in order:
python manage.py all
```

| Stage | Reads | Produces in docs/data |
|---|---|---|
| sources | Five raw inputs from the registry | source_stats.sqlite |
| normalized | Canonical GPKGs + dataset profiles | normalized_stats.sqlite |
| tiles | Paired MVT/MLT PMTiles | tile_stats.sqlite |
| audit | Source/GPKG/archive bounds and decoded tile pairs | audit_stats.sqlite |
| types | MVT protobuf values and MLT column declarations | type_stats.sqlite |
| stats | Measurement databases + SQL definitions | results.sqlite |
| report | Results + tile database and map archives | CSV, claims_report.md, tables and charts |

Measurement stages use input/code/output SHA-256 manifests to skip unchanged
inputs. `--force` rebuilds. `analyze tiles --codec-sensitivity` measures gzip-9,
Brotli-11 and Zstd-19 on unique real payloads; it is optional and can be expensive.
Run `stats` and `report` again after changing the codec measurements.

Reports write PNG/PDF into `outputs/figures`, LaTeX fragments into `outputs/tables`,
and unrounded chart/table data into `docs/data`. Exact SQL queries and CSV mappings
are included in `claims_report.md` and `claim_queries.json`. The report returns a
failure status for missing coordinate pairs, decoder/parser failures or unresolved
bounds checks while retaining its diagnostic artifacts. Strict equality differences
alone are diagnostic. The release exporter preserves failed checks for review.

The logical-zoom charts use `logical_zoom_summary` / `zoom_*.dat`; structure charts
use `analysis_sources.csv` and `analysis_normalized.csv`; gzip charts use
`analysis_gzip.csv`. Map sample geometry requires the relevant source archives;
selection addresses and attribution are in `sample_panels.json` and map manifests.

```sh
python manage.py export-dataset --output releases/dataset-v1
```

See the [dataset guide](../docs/dataset.md), [dictionary](../docs/data_dictionary.md)
and [release guide](../docs/releasing.md). The tiny integration fixture in
`tests/test_pipeline.py` exercises source profiling, real encoders, payload reuse,
full-pair validation, attribute types, SQL, tables and chart generation without
downloading any original data. `tests/test_release.py` checks the archive round-trip,
integer/NULL fidelity, empty tables, checksum rejection and source path containment.
