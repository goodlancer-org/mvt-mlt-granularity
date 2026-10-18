# Experiment Design

## Research Question

MLT is column-oriented: it can exploit repeated geometry structure, layer names, attribute keys, and semantically similar values across features. GEOMAPS asks whether larger logical vector-tile compression units improve MLT's compression relative to MVT.

The experiment emulates a sparser tile pyramid:

| Variant | Stored tile meaning | Extent |
|---|---|---:|
| Standard | normal WebMercator `z/x/y` | 4096 |
| Dense-4 | stored `z` carries Standard `z+1` detail | 8192 |
| Dense-16 | stored `z` carries Standard `z+2` detail | 16384 |

Dense-4 skips one subdivision step and Dense-16 skips two. The larger extents preserve native coordinate precision while letting one stored tile contain content that would normally be split across more smaller tiles.

## Preparation Definition

All experimental comparisons start from the same validated normalized GeoPackage.

```text
raw vector source
  -> Stage A normalized GPKG + normalization manifest
  -> Stage B Standard/Dense MVT PMTiles
  -> paired MLT PMTiles transcodes
```

Stage A owns source parsing, CRS normalization, bounds selection, source-layer naming, semantic normalization, stable identity strategy, unwanted-layer removal, and provenance. Its cost is recorded as `normalization_time_ms` and is not part of the MVT-vs-MLT encoding cost.

Stage A applies bounds once and physically clips selected geometries (`-clipsrc spat_extent`). It writes XY-only `EPSG:3857` GeoPackages with spatial indexes. Geometry fixing (`-makevalid`) is opt-in via profile normalization settings.

Stage B owns tile-layer grouping, zoom rules, simplification settings, dense variant settings, MVT generation, MVT-to-MLT transcode, and pair validation. Changing tile grouping or dense settings invalidates PMTiles outputs only, not the normalized GPKG.

Stage B trusts the canonical Stage-A contract and does not reapply spatial filtering or reprojection.

Before variant generation, Stage B performs a cheap `gpkg_preflight` against the normalized GPKG (driver/layers/fast metadata only). It does not run per-layer `ogrinfo` passes to force exact feature counts.

Validation execution modes:

- `none`: skip post-validation.
- `fast`: one MVT scan (extent + statistics) and lightweight checks during MVT->MLT transcode.
- `full`: semantic MVT<->MLT comparison during transcode.

## Controlled Variables

| Control | Value |
|---|---|
| Input scope | vector sources only |
| Normalization CRS | configurable, `EPSG:3857` by default |
| Container | PMTiles |
| MVT generation | GDAL MVT driver to MBTiles, then direct GDAL MBTiles -> PMTiles repack |
| MLT generation | tile-by-tile transcode from matching MVT |
| Simplification | shared across variants, default `1.6` / max zoom `1.0` |
| GDAL limits | very high `MAX_SIZE` and `MAX_FEATURES` |
| Concurrency | one heavy conversion job at a time |

Unknown source feature counts, such as OSM/PBF `featureCount=-1`, remain unknown in manifests and logs. They are not converted to zero.

## Stage B Execution Model

For one normalized GPKG, the normal path is:

```text
canonical.gpkg -> standard_mvt.pmtiles -> standard_mlt.pmtiles
canonical.gpkg -> dense4_mvt.pmtiles   -> dense4_mlt.pmtiles
canonical.gpkg -> dense16_mvt.pmtiles  -> dense16_mlt.pmtiles
```

Each MVT variant is produced by one GDAL job with one complete `CONF`. Multiple normalized source layers may map to one output MVT layer through GDAL `target_name`. The normal path does not generate one archive per target layer and does not merge PMTiles in Python.

For standalone Stage-B runs, profile rule selection reuses original source identity from the normalization manifest (`source_type`/`source_filename`).

Dataset-level `MINZOOM/MAXZOOM` and per-layer `CONF minzoom/maxzoom` are shifted together for Dense variants:

- Dense-4 layer zooms are Standard zooms minus 1 at the stored-tile level
- Dense-16 layer zooms are Standard zooms minus 2 at the stored-tile level
- dataset `MAXZOOM` is wide enough to include the shifted layer requests

## Validation

Stage A validation checks that the normalized GPKG opens, passes SQLite integrity, contains expected layers, has readable geometry, records bounds/provenance, and has a stable-ID strategy in the manifest. Outputs are written through `.partial` paths and are atomically renamed only after validation.

Stage B validation checks:

- MVT tile extents match the variant extent
- MVT and MLT have identical z/x/y tile sets
- layer names, feature counts, IDs, attributes, and decoded geometry match
- pair comparison streams both PMTiles archives in tile-id order rather than loading a whole archive into memory

## Metrics

Protocol/result data distinguishes:

- `normalization_time_ms`
- `normalization_peak_memory_mb` where available
- `gpkg_preflight` (seconds)
- `mvt_generation` (seconds)
- `mvt_scan` (seconds)
- `mvt_to_mlt` (seconds)
- `mlt_validation` (seconds)
- `total_postprocessing` (seconds)
- output archive size, tile count, feature count, vertex count, and per-layer summaries

Historical result tables created before this two-stage pipeline are not directly comparable. They should be treated as stale until regenerated from normalized GPKGs.

## Format Keys

| Key | Encoding | Role |
|---|---|---|
| `standard_mvt` | MVT | Standard tile pyramid |
| `standard_mlt` | MLT | Transcode of `standard_mvt` |
| `dense4_mvt` | MVT | Sparse-pyramid Dense-4 artifact |
| `dense4_mlt` | MLT | Transcode of `dense4_mvt` |
| `dense16_mvt` | MVT | Sparse-pyramid Dense-16 artifact |
| `dense16_mlt` | MLT | Transcode of `dense16_mvt` |
