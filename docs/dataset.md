# GEOMAPS research dataset

Paired MVT/MLT compression measurements for Standard, Dense-4 and Dense-16
vector-tile pyramids. Dataset DOI: [10.5281/zenodo.23452598](https://doi.org/10.5281/zenodo.23452598).

## Purpose and scope

This dataset measures how MapLibre Tiles (MLT) compares with Mapbox Vector Tiles
(MVT) in compression across five different kinds of vector maps. It supports
analysis of how compression savings depend on map content, feature and vertex
counts, attribute structure, and the spatial granularity of independently encoded
tiles. Measurements include raw payload sizes and deterministic per-tile gzip-6
sizes for Standard, Dense-4 and Dense-16 pyramids.

| Map source | Content | Original input format |
|---|---|---|
| Natural Earth | Generalized physical and cultural reference layers | GeoPackage in ZIP |
| USFWS NWI, Louisiana | Wetland and deepwater habitat inventory | GeoPackage in ZIP |
| swisstopo | Geological units and structures | Shapefiles in ZIP |
| OpenStreetMap, Louisiana | Crowdsourced transport, buildings and other map features | OSM PBF |
| PDOK BGT | Large-scale topographic infrastructure and land cover | GML in ZIP |

The measurements follow three stages: inventories of the **original sources**;
inventories of the **normalized GeoPackages used for tiling**; and measurements of
the **resulting paired MVT/MLT PMTiles archives**. They describe layer, feature,
geometry, vertex and attribute structure, encoded byte sizes, MLT streams and
validation diagnostics. These are statistics of the sources and conversion
outputs; the original maps, GeoPackages and tile archives themselves are not
included in this package. Counts at different stages have different grains:
source rows must not be equated with tiled feature instances.

The accompanying software is available at
[doi:10.5281/zenodo.23456861](https://doi.org/10.5281/zenodo.23456861).

## Files and usage

**If you need one file, download `results.sqlite`.** Start with
`variant_summary`, `granularity_gain`, `vertex_summary`, `logical_zoom_summary`
and `stream_summary`. Read `claims_report.md` before interpreting the numbers.

| Files | Use |
|---|---|
| `results.sqlite` | Materialized results, diagnostics and article metrics |
| `source_stats.sqlite`, `normalized_stats.sqlite` | Layer, geometry, field and categorical source inventories |
| `tile_stats_parquet.zip` | All tile-statistics tables in Parquet, with SQL schema and view definitions |
| `audit_stats.sqlite` | Bounds, full decoded pair checks and diagnostic examples |
| `type_stats.sqlite` | Protobuf-to-MLT attribute type profiles and transitions |
| `*_tables.zip` | Parquet and CSV tables matching each of the five SQLite snapshots |
| `analysis_*.csv`, `zoom_*.dat` | Unrounded inputs for tables and compression charts |
| `per_tile.csv` | Paired address-level features, vertices and byte sizes |
| `schema.json` | Actual columns, storage types, primary keys and exported row counts |
| `DATA_DICTIONARY.md`, `SOURCES.md`, `sources.json` | Interpretation, attribution and source identity |
| `provenance.json`, `*.manifest.json`, `conversion_protocols/` | Export environment, measurement fingerprints and available conversion records |
| `SHA256SUMS` | SHA-256 of every distributed file except the checksum list itself |

Tile measurements use **Parquet as their primary storage format**:
`docs/data/tile_stats/` locally, `tile_stats_parquet.zip` in a release. Each table
has its own Zstandard-compressed Parquet file, including typed empty tables.
`schema.json` records columns, integer/NULL types, logical keys and row counts;
`schema.sql` records table definitions and reusable view queries. Parquet does not
enforce SQL constraints or store indexes. The analysis and reports query these
files directly with DuckDB; a temporary DuckDB workspace is used while measuring
new archives and removed after writing Parquet. No tile-statistics SQLite database
is created, retained or published.

The other five databases remain available as SQLite snapshots with corresponding
Parquet/CSV bundles. SQLite snapshots are consistent individually; do not modify
any analysis outputs during export. CSV uses UTF-8, a header and empty cells for
NULL. Use SQLite or Parquet when empty string versus NULL matters. Parquet preserves
64-bit integer values and NULLs, without converting large integers to float.
`tile_stats.manifest.json` records the inputs and fingerprints of the Parquet store.

Extract `tile_stats_parquet.zip` into a separate directory to avoid table-name
collisions with the other bundles. For an LLM service, upload only the relevant
Parquet table or a filtered/aggregated extract; the full tile corpus is not needed
for most questions. For high-level article metrics, start with `results.sqlite`
or the smaller `analysis_*.csv` files.

```python
from zipfile import ZipFile
import pandas as pd
import duckdb

with ZipFile("tile_stats_parquet.zip") as bundle:
    bundle.extractall("tile_stats")

# A reader only needs Parquet support; DuckDB is optional for custom queries.
tiles = pd.read_parquet("tile_stats/tiles.parquet")
with duckdb.connect() as con:
    summary = con.execute("""
        SELECT archive_id, count(*) AS n_tiles, sum(raw_payload_bytes) AS raw_bytes
        FROM read_parquet('tile_stats/tiles.parquet') GROUP BY archive_id
    """).df()
# For large tables, select columns or use pyarrow.parquet.ParquetFile.iter_batches().
```

```python
import sqlite3
import pandas as pd

with sqlite3.connect("results.sqlite") as con:
    results = pd.read_sql_query("SELECT * FROM variant_summary", con)
print(results)

# Extract results_tables.zip first:
same_table = pd.read_parquet("variant_summary.parquet")
```

Tile summaries are address-weighted; MLT stream summaries count unique stored
payloads. Savings are ratios of sums, not averages of per-tile savings. Original
source maps and PMTiles archives are distributed separately, if at all; none are
required to query the measurements. Full regeneration requires matching sources.

The release command does not certify scientific claims. Failed or pending checks
are preserved in `claims_report.md`. Strict decoded equality is diagnostic;
missing addresses and decoder errors are failures. Normalized-feature completeness
and independent parser cross-checks remain limitations.
