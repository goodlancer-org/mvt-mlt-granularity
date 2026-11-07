# Extended granularity experiment

This is the primary experiment. The earlier three-variant, Python-produced study
is historical; its archives and measurements must not be mixed with this corpus.
The design is [extended_experiment_design.md](extended_experiment_design.md).

## Reproduction

Start with the same five normalized GeoPackages and dataset profiles listed in
`analysis/datasets.json`. Source data, study regions and normalization do not change.

```powershell
python manage.py build
python manage.py experiment
python manage.py all
python manage.py tex build --tex-file paper/latex/_main.tex
```

`experiment` runs `src.experiment` in the GDAL Docker image. It accepts repeatable
`--dataset <registry-id>` and `--force`. `all` imports completed measurements,
builds extended summaries and regenerates article tables, the logical-zoom plot
and the curated three-zoom map panels. Normalized/source inventories are reused
from the unchanged source data; their separate commands remain `analyze sources`
and `analyze normalized`. `analysis.pipeline --legacy` explicitly selects the old
analysis implementation. Compile the existing LaTeX source with `tex build`;
the old Markdown-to-paper command is not the source of the extended manuscript.

Direct analysis commands, without a Docker dependency:

```text
python -m analysis.extended tiles
python -m analysis.extended stats
python -m analysis.extended report
```

On a host with Rust 1.98.1 and a native toolchain, build the same adapter with
`python app/converter/build_mlt_cli.py`. Set `MLT_RUST_CLI` to override its executable.
The Docker image already includes the Linux executable and its build manifest.

Conversion and encoding can also be overlapped across completed datasets:

```text
python manage.py experiment --mvt-only
python -m analysis.encode --workers 2 --wait
```

Run those commands in separate terminals. The host encoder waits for completed
generation manifests and uses one pinned host Rust build for both versions and
every variant. Its actual binary/build identity is recorded; do not silently
attribute host-produced outputs to the Linux executable. Docker performs GDAL
generation and also supports the complete conversion/validation path directly.
The observed primary host environment, including archive-I/O and zlib versions,
is recorded in `docs/validation/extended-run-environment.json`; this run used
PMTiles Python 3.7.0, whereas the clean Docker dependency set pins 3.8.1. Encoder
identity and the independently recompressed tile-size measurements are recorded
separately from physical archive packaging.
The recorded run also used two additional workers for Swiss/USFWS and then
disjoint PDOK variants while the primary scheduler was paused and its active
workers continued. The scheduler resumed after each separate batch to avoid
overlapping variant writes. The runtime manifest records this four-task concurrency. Elapsed times
are diagnostic and are not controlled encoder-throughput measurements.

Interrupted runs reuse a completed variant only after its input/build identities,
archive checksums and measurement checksum match. Exact aggregates additionally
verify their source and equivalence-evidence checksums. An incomplete variant is
encoded again; a partial archive is not accepted as a completed result. The
recovery after a closed terminal is recorded in the execution-environment manifest.

## Conversion and provenance

Each normalized source layer keeps its attributes and geometry. Disjoint offsets
turn its original GeoPackage FIDs into globally unique IDs within a dataset.
`app/data/provenance/<dataset>.provenance.sqlite` maps each ID to its original
source layer and FID. The derived `.provenance.gpkg` changes only these FIDs;
exhaustive SQL joins verify every non-FID cell, including the geometry BLOB,
against the original. Spatial-index IDs are remapped and triggers restored.
No provenance property is added to the tile attribute schema.

A read-only VRT describes the equivalent ID projection. For performance the actual
GDAL conversion reads the materialized GeoPackage: VRT SQL can disable fast GPKG
reading. SQLite-heavy scratch work uses the container's disk-backed Linux
filesystem (`MLT_EXPERIMENT_SCRATCH`, default `/tmp/mlt-experiment`), then exports
finished artifacts to `/data`. This avoids random SQLite I/O over Windows bind
mounts. The original normalized files are never modified.

Standard and Dense retain the historical generation rules: extents are
4096/8192/16384 and GDAL BUFFER values are 80/160/320, respectively; simplification
and logical-zoom layer-selection rules remain fixed. Thus Dense's exterior buffer
does not equal the translated outer buffer of an exact aggregate. This is part of
the measured regeneration intervention, not a clipping-only control.
IDs are retained using `ogr2ogr -preserve_fid`. The new IDs
are encoded content, so new sizes are not directly substituted into old conclusions.

| Variant | Area | Extent | Logical zoom |
|---|---:|---:|---|
| Standard | 1 | 4096 | stored z |
| Aggregated-4 | 4 | 8192 | stored z + 1 |
| Aggregated-16 | 16 | 16384 | stored z + 2 |
| Dense-4 | 4 | 8192 | stored z + 1 |
| Dense-16 | 16 | 16384 | stored z + 2 |

`mvt_aggregate.py` translates integer geometry commands, preserves feature IDs,
typed values, fragments and multiplicities, and pools MVT key/value dictionaries
across children. Pooling also gives MVT the larger dictionary scope; concatenating
redundant dictionaries would unfairly handicap the MVT control. An independent
parse verifies the exact translated feature multiset after serialization. No
deduplication, geometry merging, extra simplification or regeneration occurs.
Incomplete boundary blocks contain their present children, without invented empty tiles.

## Rust codec

The adapter calls official `mlt-core 0.22.1`, from the `maplibre-tiles 0.4.1`
source distribution. The source checksum is
`dd35bb6771b59006efd505afb102334e37e1af53b17e640d3a6438e917663aa3`.
The corresponding upstream commit is
`e7bc737dc96f734a8549a41844b8aaf43ee50723`.

Both versions use Native/4G, sorting off, tessellation off, FSST/FastPFOR/shared
dictionaries on. V2 packed dictionary codes remain on; ALP, float dictionaries,
delta2 and rANS vertices remain off. The Cargo lockfile fixes transitive versions.
Each `.experiment.json` records source, adapter, binary and Rust identities and options.
The adapter is research plumbing, not the upstream `mlt` executable. Its codec
algorithms are upstream; `rust/src/verify.rs` vendors the pinned official verifier
with explicit budget constructors. Budget-only patches expose the MVT importer's
Buffa element-memory limit and the read-only annotated walker's limit, leaving
their original APIs/defaults intact. The build verifies the `fast-mvt 0.7.1`
crate checksum before applying its constructor patch; Cargo dependencies remain
locked. Encoding algorithms are unchanged.

`MLT_DECODE_MEMORY_MIB=256` passes 256 MiB to Rust MVT import and MLT parse/decode/annotation. This is
an internal allocation guard, not an RSS limit or Docker quota. The old 20 MiB
guard rejected 48 addresses; stock 0.4.1 at 64 MiB still rejected 17 of those.
See `docs/validation/mlt-0.4.1.md` for the historical investigation. That audit's
strict typed/geometry differences are not silently reclassified as equal here.

The largest regenerated PDOK Dense-16 tile also exposed a separate upstream
32 MiB Buffa element-memory guard while importing MVT (`protobuf decode error:
element memory limit exceeded`). Raising the MLT budget alone to 512/1024 MiB
did not affect that earlier stage. The adapter therefore passes the explicit
budget through the MVT reader as well. Before/after diagnostic evidence is in
`docs/validation/extended-max-dense16-budget*.json`; full acceptance remains the
corpus-wide report, not this diagnostic subset.

Native round trips compare the decoded output with the **Rust-imported** MVT layer.
They allow the official verifier's integer-width, polygon-winding and null/absent
normalizations. Mixed MVT property types can unify to strings before encoding.
`extended_attribute_summary.csv` measures original wire types versus imported
column types; `extended_validation_summary.csv` reports source/imported feature
and vertex differences. A passing native round trip is not strict protobuf or
map-style equivalence. Aggregation has its independent exact typed multiset gate.
That exact control applies at the MVT input boundary. Larger units can place
previously separate value types into one MLT column and cause additional type
normalization. The measured fixed-input byte effect includes this constraint;
type transitions are reported, not independently controlled as a codec mechanism.

## Measurements and comparisons

Every dataset has five MVT inputs and ten MLT outputs, named
`<dataset>_<variant>_<mvt|mltv1|mltv2>.pmtiles`. Payloads are also measured raw and
after independent gzip level 6 with timestamp zero. Original stored MVT lengths
are retained separately. Address-weighted transfer totals differ from unique
payload storage and complete archive sizes.

For each logical zoom, parent z/x/y identifies a comparison block. The additive
decomposition uses the intersection of Standard parent blocks, Aggregated blocks
and Dense blocks; the coverage export reports boundary omissions. For one format
and compression state on that support:

```text
total_reduction_bytes = standard_bytes - dense_bytes
aggregation_reduction_bytes = standard_bytes - aggregated_bytes
regeneration_reduction_bytes = aggregated_bytes - dense_bytes
total_reduction_bytes = aggregation_reduction_bytes + regeneration_reduction_bytes
```

All component percentages divide by the same Standard total. They are distinct
from MLT-versus-MVT savings and their percentage-point differences.
Regeneration includes clipping, buffering and representation; it is not labeled
as a clipping-only effect.

Unique source-feature counts use provenance IDs within a logical zoom, including
all selected source layers. These IDs identify normalized source records, not
real-world entities deduplicated across layers. Repeated instances share an ID.
Stored vertices are explicit MoveTo/LineTo coordinates, excluding implicit ring
closure; MoveTo parts include rings, multipart lines and point components.
Repeated vertices share ID and local coordinates within the same comparison block.
These observable counts do not causally separate buffering from clipping.

## Memory and intermediate storage

Detailed analytical observations are written in bounded Arrow batches to
Zstandard-compressed Parquet, including the potentially large source-ID,
attribute and stream tables. DuckDB scans these files directly with a 4 GiB
query-memory limit; `extended/results.sqlite` contains only aggregate results.
The extended pipeline does not create a per-tile analytical SQLite database.

SQLite remains appropriate for the source-ID lookup (approximately 0.04--10 MB
for the five datasets) and the unchanged source/normalized inventories
(approximately 11 MB and 7 MB). Historical `results.sqlite` and
`type_stats.sqlite` are approximately 1 GB each; they are retained as historical
outputs, are not expanded by this experiment and are not primary analysis inputs.

GDAL's GeoPackage and temporary MBTiles are SQLite-based geospatial formats,
rather than analytical intermediates that can be replaced with Parquet. Derived
GeoPackages and tile-generation work use the container's disk-backed Linux
scratch directory (`MLT_EXPERIMENT_SCRATCH`, default `/tmp/mlt-experiment`), not
shared memory or a Windows bind-mounted SQLite database. Completed archives and
the provenance lookup are exported to `app/data`; scratch tiles are removed after
successful generation. Source and normalized inputs remain unchanged.
Extracted source caches under `docs/data/.analysis_cache/extracted` can be removed
and rebuilt from the source archives; they are not experimental outputs.

`MLT_DECODE_MEMORY_MIB=256` is a Rust parser/decoder/walker allocation budget per
tile, not the Docker RAM quota or a bound on process RSS. Increase it only in
response to an observed budget error and record the value in the conversion
manifests. Docker must additionally accommodate GDAL, the encoder and its workers.

The version-aware native walker classifies all frame bytes. Structural share is
`(frame_bytes - stream_payload_bytes) / frame_bytes`. Integer RLE lengths are
expanded before computing logical values/stream and payload bytes/value, because
v1 and v2 header counts use different conventions. Coordinate pairs count as one
vertex value; booleans count logical positions. Different roles remain mixed, so
these ratios are descriptive. Structure is counted per unique MVT payload input;
headline sizes are address-weighted. They must not be algebraically conflated.

## Output layout

- `app/data/output/*.generation.json`: GDAL commands, source/profile identities.
- `*.experiment.json`: codec provenance, archive hashes, validation and timings.
- `*.measurements.jsonl.gz`: address/payload/content/codec measurements.
- `*.aggregation.jsonl.gz`: exact multiset equivalence evidence by parent block.
- `*.aggregation.json`: source/archive/evidence checksums for safe aggregation reuse.
- `docs/data/extended/`: partitioned Parquet tables and `results.sqlite` summaries.
- `docs/data/extended_*.csv`: unrounded inputs for tables and figures.
- `docs/data/extended_claims.json`, `extended_checks.md`: executable claim queries
  and acceptance checks.
- `paper/latex/tables/extended_*.tex`: generated table rows and numerical macros.
- `paper/latex/figures/analysis_zoom_aligned.*`, `map_*`: generated visualizations.

The Parquet tables are `addresses`, `payloads`, `content`, `feature_ids`, `streams`,
`frames`, `attributes`, `validation`, `equivalence`. Their explicit Arrow schemas
are in `analysis/extended.py`; the reproducible transformations are in
`analysis/sql/extended.sql`. `payload_key` links unique MVT inputs to every address
and both encoded versions. Region provenance is the unchanged dataset profile and
source hash in generation manifests. `feature_ids` links to the separate source lookup.

Statistics also reopen every physical PMTiles archive. They check every address,
raw length and payload SHA-256 against the measurements: raw MVT hashes and the
exact gzip-encoded MLT bytes that passed native verification. Missing, duplicate,
unexpected or changed addresses/payloads fail the stage. Actual MVT gzip bytes are
checked against stored input lengths, separately from canonical recompressed
gzip-6 sizes. `extended_physical_archives.csv` records this independent I/O audit.

Historical archives are copied before replacement into
`app/data/historical/python-0.2.2/`; their checksum manifests are retained.
Original canonical protocol JSONs are retained under its `protocols/` directory.
The new canonical protocol and `.extended.json` companion expose all 15 outputs;
API listing uses the canonical file once, and MVT/MLT aliases refer to Standard
MVT and Standard MLT v1 rather than the historical archives.
Historical analysis exports are snapshotted in `docs/data/historical/python-0.2.2/`.
The old Parquet inventory and source/normalized inventories remain available.
No Zenodo record is published automatically: `zenodo/` is the local software/data
mirror prepared for review and later release.
