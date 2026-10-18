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
| `tile_stats.sqlite` | Address-level measurements and unique-payload MLT streams |
| `audit_stats.sqlite` | Bounds, full decoded pair checks and diagnostic examples |
| `type_stats.sqlite` | Protobuf-to-MLT attribute type profiles and transitions |
| `*_tables.zip` | One independent bundle per database: matching table-by-table Parquet and CSV |
| `analysis_*.csv`, `zoom_*.dat` | Unrounded inputs for tables and compression charts |
| `per_tile.csv` | Paired address-level features, vertices and byte sizes |
| `schema.json` | Actual columns, storage types, primary keys and exported row counts |
| `DATA_DICTIONARY.md`, `SOURCES.md`, `sources.json` | Interpretation, attribution and source identity |
| `provenance.json`, `*.manifest.json`, `conversion_protocols/` | Export environment, measurement fingerprints and available conversion records |
| `SHA256SUMS` | SHA-256 of every distributed file except the checksum list itself |

Every table bundle is produced from the accompanying SQLite snapshot, including
empty tables. Parquet preserves integer values and NULLs. CSV uses UTF-8, a header,
and empty cells for NULL; use SQLite or Parquet when empty string versus NULL matters.
SQLite views remain in SQLite; bundles contain materialized tables only.

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
