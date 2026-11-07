> **Primary experiment update (2026-11-06).** Five variants (Standard, Aggregated-4/16, Dense-4/16), MVT and Rust MLT v1/v2, source-feature provenance and matched-block effect decomposition are now defined in [the extended experiment guide](../docs/extended_experiment.md). Run `python manage.py experiment`, then `python manage.py all`. Primary summaries live in `docs/data/extended/results.sqlite`; generated CSV/TeX files use `extended_` prefixes. The three-variant Python workflow and numerical claims below describe the historical study.

# Paper analysis

Run from the repository root using the existing host environment:

```powershell
.venv/Scripts/python.exe management.py all
# manage.py is the same entry point; management.py is a compatibility spelling.
.venv/Scripts/python.exe manage.py analyze sources
.venv/Scripts/python.exe manage.py analyze normalized
.venv/Scripts/python.exe manage.py analyze tiles
.venv/Scripts/python.exe management.py audit
.venv/Scripts/python.exe management.py types
.venv/Scripts/python.exe manage.py stats
.venv/Scripts/python.exe manage.py report
```

`all` runs the three measurements, the bounds/full-pair audit, attribute types, statistics and report in order. Measurement
and statistics stages use SHA-256 manifests to skip unchanged inputs. `--force`
rebuilds. `analyze tiles --codec-sensitivity` additionally measures gzip-9,
Brotli-11 and Zstandard-19 per unique stored payload; this can take much longer.
Dependencies are in the root `requirements.txt`; `manage.py env sync` installs them.

`datasets.json` lists the five existing raw inputs, normalized inputs and current
converter profiles. For this analysis all source inputs are selected explicitly under
`app/data/sources/<id>/`: four original ZIP archives and the OSM PBF. Extracted or
prepared neighbours are not counted again. These selected files were SHA-256 verified
against the former `data/map/datasets` inputs. The converters and semantic layer names
remain unchanged.

Tile measurements use Parquet as their permanent working format. Statistics and
reports query them directly with DuckDB. A temporary DuckDB build workspace is
removed after Parquet publication. To recompute summaries from the existing
measurements, run `manage.py stats` and `manage.py report`. For custom analysis,
read the needed Parquet tables/columns with DuckDB, pandas or PyArrow; see
[the dataset guide](../docs/dataset.md). Dataset export creates
`tile_stats_parquet.zip` and five SQLite snapshots with their Parquet/CSV bundles.

Outputs:

- `docs/data/{source,normalized}_stats.sqlite`, `results.sqlite` and hash manifests;
- `docs/data/tile_stats/`: Parquet tile tables, `schema.json`, `schema.sql`, with
  `docs/data/tile_stats.manifest.json`; no SQLite copy is created or retained;
- `docs/data/audit_stats.sqlite`: bounds at all four stages, checks, full decoded pair
  validation and capped diagnostic examples;
- `docs/data/*.csv`, sample panel coordinates and `claims_report.md`;
- `paper/latex/tables/analysis_*.tex` (requires `booktabs` and `longtable`);
- `paper/latex/figures/analysis_*.pdf` and 600-dpi PNG counterparts.

The `analysis_*.tex` tables are standalone `longtable` environments. The article
instead includes `paper_*_rows.tex` inside its existing table layouts, preserving
captions and labels. `paper_tables.py` generates raw/normalized structure,
measured variant parameters, compression, vertex bins, stream structure and
bytes/vertex rows, plus `paper_numbers.tex` for the pooled table caption.
`report` regenerates both kinds of tables. To refresh only article tables from
the existing results and Parquet measurements, without rerunning measurements or rendering figures:

```powershell
.venv/Scripts/python.exe -m analysis.paper_tables
```

Provenance is editorial metadata and remains in `ch03_method.tex`; the external
traffic table in `ch07_appendix.tex` remains manual until raw traffic inputs are
available. `fig_zoom_aligned.tex` includes the combined `analysis_zoom_aligned.pdf`
computed directly from SQLite. Dataset samples in the article are generated separately by `manage.py maps`
(see below). The older `analysis_sample_*` report panels remain diagnostic alternatives.
Conceptual diagrams remain unchanged.
Broader prose integration remains an editorial step.

`sql/00_*.sql` through `18_*.sql` materialize the existing SQL analysis, without
intermediate rounding, plus paper metrics. The original two SQL scripts are
preserved here for reference/export; copies in `docs` remain until results are
reviewed. Source and normalized databases preserve the original analyzer's full
schema, including fields, values, semantic classes and diagnostics.

`gzip_payload_bytes` is recomputed from decompressed bytes with Python gzip,
level 6, `mtime=0`, for both formats. `stored_bytes` records archive storage.
`gzip_check` compares lengths (not byte-for-byte gzip stream equality).
`gzip_impact` reports the change in headline savings relative to using stored bytes.
Tile summaries are address-weighted; stream summaries are payload-weighted.
`content_offset` together with archive ID and stored length identifies a payload.
Structure summaries retain `fields` as the sum of per-layer field counts used in
the article and also store `distinct_fields` as dataset-wide distinct field names.

Reports write artifacts before failing on an unsuccessful check. Bounds are
checked with a `1e-5` degree tolerance, and absent declared bounds stay unknown.
Unknown geometry counts stay NULL; raw geometry-less fallbacks are diagnostic.
`management.py audit` reads actual feature envelopes from selected source files and
GPKGs using OGR `read_bounds` (including curved geometries), records native CRS/bounds
and WGS84 envelopes, and keeps each layer/component plus the dataset union. Profile
rules are selected using the converter's own matching code. Rule/profile/normalization
manifest bounds are separate records; absent historical manifests stay unknown.
No external geographical bounds are downloaded or inferred.
For CRS-less PDOK GML, native envelopes remain unchanged. Separate source records
with `kind=geometry_pipeline_crs` use the converter's configured CRS fallback
(`citygml_fallback_source_srs` in `app/converter/config.yaml`), and explicitly record
the config hash and absent declared CRS. This projection is not a historical claim.

For all 15 MVT/MLT pairs, the audit reads archive directories and payloads, records
header/metadata bounds, addressed-cell coverage, and independently decoded geometry
envelopes by layer/zoom and dataset. Full validation compares layer names, extents,
typed attribute values, IDs and canonical geometry feature multisets at every address.
Feature order, ring start/orientation and multipart ordering are ignored; duplicates,
vertices and geometry types are preserved. Absent feature IDs equal protobuf default
zero, matching the converter convention. Properties are not stringified. Missing
addresses, decoder errors and content mismatches fail validation; details are capped
at 200 examples per pair, while counts cover every address.
Polygon mismatches also carry a diagnostic comparison of wire-level MVT rings with
MLT WKB rings. Zero-area rings can be dropped by the MVT GeoJSON decoder but retained
by MLT; matching wire rings do not override a failed decoded-geometry comparison.
Source/configuration/GPKG envelopes have a separate hash/code/version-keyed cache,
so archive revalidation need not repeat unchanged source scans.

`bounds_checks` distinguishes `pass`, `fail` and `unknown`. Checks include normalized
geometry versus source/current configured bounds, profile/rule agreement, and tile
geometry versus normalized bounds (one coordinate-grid unit tolerance) and tile buffer
(the converter's 80*2^d units plus one grid unit). Archive bounds/cell coverage are
descriptive and are never substituted for geometry bounds. Current config does not
prove historical settings. `stats` copies audit tables to `results.sqlite`; `report`
exports `bounds.csv`, `bounds_checks.csv`, `validation.csv`, `validation_issues.csv`,
`validation_examples.json` (bounded typed-attribute witnesses), and
`analysis_validation.tex`, and requires complete independent decoding and address
coverage. Strict typed equality is diagnostic, not an acceptance gate.
The existing `validation.passed` retains strict equality for compatibility; its
exported table heading now explicitly says "Strict equality".

`management.py types` builds `docs/data/type_stats.sqlite` from the existing 30
archives without decoding geometry. It reads exact MVT protobuf types and MLT v1
column metadata (including SharedDict children), scoped to a layer within a tile.
`stats` copies all six tables to `results.sqlite`; `report` exports:

- `attribute_transitions.csv`: dataset/variant/layer/property, before_type,
  after_type, nullability/storage and address-weighted value counts;
- `attribute_type_summary.csv`: mixed-type column/tile counts and original non-string
  values assigned to string columns;
- `attribute_type_errors.csv`: explicit unknown/error cases;
- `paper/latex/tables/analysis_attribute_types.tex`: supplementary summary table.

Details in `attribute_type_profiles` are stored per pair of payload locations;
`attribute_tile_addresses` preserves every address. Absence counts repeat across
original-type rows; do not sum them across those rows. Transitions describe column
assignments, not matched-object values. Numeric changes do not prove preserved
values; nullability does not measure actual nulls. Bounded source-value examples
are diagnostics, not paired before/after values.
Profiles describe output layers. They cannot identify which original source layer
contributed a value after several source layers were merged.

For example, to inspect non-string MVT values assigned to MLT string columns:

```sql
SELECT dataset_id, variant, layer_name, property_name,
       before_type, after_type, value_occurrences,
       mixed_source_value_occurrences
FROM attribute_transitions
WHERE transition = 'to_string'
ORDER BY value_occurrences DESC;
```

To locate the exact tiles and original value examples, join
`attribute_type_profiles` to `attribute_payload_pairs` and
`attribute_tile_addresses` using `pair_id`. A profile's `value_count` counts values
within one payload; `attribute_transitions.value_occurrences` already includes
address multiplicity. Do not multiply the latter again.

Completeness by stable feature ID, independent parser reference checks, full data dictionaries, traffic integration,
and release packaging remain tracked in `docs/pipeline.md`.

Tests use real GPKG, MVT and MLT encoders and the full SQL/report path:

```powershell
.venv/Scripts/python.exe -m unittest discover -s analysis/tests -v
```

## Article map illustrations

```powershell
.venv/Scripts/python.exe manage.py maps --build
```

Or run `python manage.py` and select **maps --build**. The command discovers every
final `*_standard_mvt.pmtiles` in `app/data/output`, renders three views per map,
and builds `paper/latex/_main.pdf`. MLT, Dense variants and converter scratch files
are excluded. `manage.py maps` renders only. Options are `--regions`, `--input-dir`,
`--output-dir` and `--dpi` (default 450). The article groups all five datasets into
**one figure on one page**, with three map columns and a LaTeX description column.
Only geometry and magenta next-view outlines are drawn into image assets; zooms,
region names, palette descriptions and attribution are typeset in LaTeX.

### Region configuration and measurement provenance

`analysis/map_regions.yaml` is the source of truth for the curated zooms, tile
addresses and visible areas. Selection is fixed, rather than recomputed using a
maximum-complexity or archive-center heuristic:

| Dataset | Zooms | Selected XYZ tile addresses |
|---|---|---|
| Natural Earth | 5, 7, 9 | 5/9/12; 7/37/48; 9/150/192 |
| Dutch BGT | 12, 13, 14 | 12/2114/1355; 13/4229/2711; 14/8458/5423 |
| USFWS wetlands | 10, 12, 14 | 10/255/424; 12/1023/1697; 14/4092/6789 |
| swisstopo | 10, 12, 14 | 10/538/359; 12/2154/1436; 14/8617/5745 |
| OSM Louisiana | 10, 12, 14 | Same as wetlands, for direct spatial comparison |

The first four selections come from the earlier `bench/figures/*_fig.py` scripts,
whose tile inventories used the `archives` and `tiles` tables in **`data/output.sqlite`**.
The old absolute Linux path is no longer needed. The current inventory is
**`docs/data/tile_stats/` (Parquet)**; **`docs/data/audit_stats.sqlite`** contains measured
geometry envelopes by dataset, format, variant, layer and zoom. There are currently
no SQLite files directly in `analysis/`. The five curated selections were checked
against the current inventory, restricted to Standard MVT.

Each YAML panel contains:

- `z`, `x`, `y`: the fixed stored tile address;
- `level_bounds`: `[west, south, east, north]` in WGS84 degrees, frozen from the
  intersection of the archive bounds and the decoded geometry envelope at that zoom;
- `view_bounds`: the visible square in Web Mercator, expressed as WGS84 bounds.
  It lies inside both the selected tile and `level_bounds`;
- the dataset's `region`: the human-readable area name used in the LaTeX description.

Viewports use the largest square fitting the selected tile/data intersection,
placed toward the center of the finest selected tile. This removes margins outside
the dataset bounds without changing the curated zooms or tile addresses. Natural
empty areas inside a data envelope can still occur: an envelope is not a coverage mask.
Wetlands and OSM retain identical viewports. Magenta rectangles show the **actual
next viewport**, including its crop, rather than assuming a full child tile.

To change a region, edit its three YAML panels and rerun `manage.py maps --build`.
Coordinates must be finite and ordered; tile addresses and viewports must be nested,
zoom levels increasing, and viewports square in Web Mercator. The generator fails
on invalid configuration, missing/empty tiles or a viewport outside the current
archive bounds. All geometric validation happens before rendering; current archive
bounds are also checked when reading each configured panel.

The measured inventory and audit values are frozen into YAML for repeatability. Rendering reads PMTiles
and YAML directly and does not depend on an SQLite connection, a server or downloads.
If archives are regenerated with different bounds, inspect the updated inventory/audit
before editing the YAML; the old selection is never silently replaced. For a new
archive absent from YAML, a generic layer style and automatic nonempty nested tile
selection remain available; curate its YAML entry before using it in the article.

For example, check a configured address in the current inventory with:

```sql
SELECT t.z, t.x, t.y, t.stored_bytes
FROM tiles t
JOIN archives a ON a.id = t.archive_id
JOIN maps m ON m.id = a.map_id
WHERE m.dataset_name = 'natural_earth_vector'
  AND m.variant = 'standard' AND a.format = 'MVT'
  AND t.z = 5 AND t.x = 9 AND t.y = 12;
```

### Implementation and outputs

`analysis/map_figures.py` validates YAML, discovers archives, decodes tiles, applies
viewport crops, draws next-view outlines and exports the article figure.
`analysis/map_styles/drawing.py` draws polygons (including holes), lines and points;
`map_styles/*_fig.py` contain dataset-specific styling, without hard-coded regions.
The NWI, BGT and Natural Earth palettes reuse the earlier figure scripts. Swisstopo
uses the existing legend colors and current `SYMBOL`/`INDEX_` attributes, without the
old feature-id/spatial join. OSM uses retained tags, including `other_tags`, because
its merged `buildings` layer contains other feature kinds too.

Outputs in `paper/latex/figures`:

- `map_<dataset>_z<zoom>.{png,pdf}`: square, text-free map panels. PDF collections
  are rasterized at the requested DPI to avoid enormous vector files;
- `map_samples.tex`: the single page figure included by `ch03_method.tex`;
- `map_samples.json`: archive SHA-256, YAML path/hash, tile addresses, viewport and
  level bounds, per-tile feature counts, approximate tile/view side lengths and color inventory;
- `map_samples_color_key.md`: readable color tables. Counts cover complete decoded
  tiles across the three zooms, including buffered/off-viewport features, rather
  than only features visible after cropping.

LaTeX builds use `.compile-check/tex/_main` for intermediate files, run BibTeX and
resolve references before copying the completed PDF to `paper/latex/_main.pdf`.
This avoids collisions with an editor building in the source directory.

Validate decoding, OSM classification, YAML bounds and exports with:

```powershell
.venv/Scripts/python.exe -m unittest analysis.tests.test_map_figures -v
```

## Codec upgrade

The analysis dependency is pinned to `maplibre-tiles==0.4.1`, matching new
converter runs. Repeat validation reads the retained MVT/MLT archives without
re-encoding them or changing compression measurements. Historical measurement
metadata continues to describe the environment that produced each artifact.

Validation passes `MLT_DECODE_MEMORY_MIB` (default 256 MiB) to the budget-enabled
Rust binding built by `python app/converter/build_mlt.py --install`. Both the
codec version and memory budget are included in audit cache keys and metadata.
The upstream 0.4.1 default of 64 MiB still fails on 17 of the 48 previously
failing tile addresses; 256 MiB decodes all 48. Strict content differences remain
a separate diagnostic from successful decoding and address coverage.
