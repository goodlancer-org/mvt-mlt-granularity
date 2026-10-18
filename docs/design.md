# GEOMAPS Design

GEOMAPS is a vector-only research platform for comparing MVT and MLT under Standard, Dense-4, and Dense-16 tile granularities. The central artifact is no longer a raw source file or an intermediate MBTiles archive; it is a validated normalized GeoPackage that can be reused for many tile experiments.

## Architecture

```text
raw vector source
    |
    v
Stage A: normalize
    |
    v
canonical normalized GeoPackage
    |  + <dataset>.normalization.json
    |
    v
Stage B: tile experiment
    |-- one GDAL MVT->MBTiles->PMTiles job -> standard_mvt.pmtiles -> standard_mlt.pmtiles
    |-- one GDAL MVT->MBTiles->PMTiles job -> dense4_mvt.pmtiles   -> dense4_mlt.pmtiles
    `-- one GDAL MVT->MBTiles->PMTiles job -> dense16_mvt.pmtiles  -> dense16_mlt.pmtiles
```

## Data Directories

| Directory | Role |
|---|---|
| `/data/sources/` | downloaded or uploaded raw vector sources |
| `/data/normalized/` | canonical GPKG artifacts and normalization manifests |
| `/data/output/` | measured MVT/MLT PMTiles archives |
| `/data/protocols/` | compact protocol summaries for UI/results |
| `/data/logs/` | stage logs and diagnostics |

`.partial` outputs are never treated as complete cache hits. Normalization and tile-generation fingerprints are separate: changing bounds or semantic normalization invalidates the GPKG, while changing tile-layer grouping invalidates PMTiles only.

## Stage A

`src/normalize_source.py` builds the canonical GeoPackage contract (with core cache/manifest helpers in `src/normalization.py`):

- GDAL-readable vector sources are converted to GPKG
- CRS normalization defaults to `EPSG:3857`
- geometry is coerced to 2D (`XY`) during normalization
- bounds are applied once with `-spat` and physically clipped with `-clipsrc spat_extent`
- normalization schema version is `2`; cache artifacts from older schema versions are invalidated
- `-makevalid` is opt-in (`profile.normalization.make_valid=true`), not unconditional
- cache fingerprint includes Stage-A normalization rules and excludes Stage-B tiling zoom/layer mapping rules
- source hash, normalization rules hash, CRS, bounds/clip mode, layer counts, stable-ID strategy, warnings, GDAL version, and GPKG hash are written to `<dataset>.normalization.json`
- output is written to a temporary path and atomically renamed after validation

The manifest is required. Embedding extra GPKG metadata is allowed, but the sidecar is the reproducibility contract.

## Stage B

`src/gdal_tiles.py` reads only normalized GPKG inputs in the normal path. Per variant, Stage B writes MVT tiles with the GDAL MVT driver into MBTiles, then repacks them into PMTiles via direct GDAL translation.

Stage B preflight is intentionally cheap: one `ogrinfo -ro -json` pass is used to validate the input driver (`GPKG`), enumerate layers, and collect fast metadata. Missing feature counts remain unknown rather than triggering per-layer source scans.

Stage B enforces the canonical normalized contract (XY + `EPSG:3857`) and therefore does not reapply `-spat/-spat_srs` filtering or `-t_srs` reprojection. For unfiltered GPKG reads, GDAL is configured with `OGR_GPKG_NUM_THREADS=4`.

The profile plan keeps source-layer normalization separate from output tile grouping:

```text
raw source layer -> normalized source layer -> Stage B output MVT layer
```

Several normalized source layers can map to the same output layer through GDAL `target_name`. The normal path no longer creates per-target-layer PMTiles archives, no longer runs `pmtiles convert` from MBTiles, and no longer decodes/re-encodes MVT tiles in Python to merge layers.

When Stage B is run standalone, profile selection keeps the original source identity by reading `source_type`/`source_filename` from the normalization manifest, rather than deriving profile rules from the normalized GPKG identity.

MLT is always a transcode from its paired MVT archive. Pair validation streams both PMTiles archives in tile-id order.

## API And UI Responsibilities

The UI/API should expose two explicit operations:

1. Normalize source
   - choose or upload a raw vector source
   - preview the normalization/profile plan
   - run Stage A
   - inspect layers/counts/manifest
   - download the GPKG and manifest bundle

2. Generate MVT/MLT
   - choose an existing normalized GPKG
   - preview tile-layer mapping and dense settings
   - generate Standard, Dense-4, and Dense-16 outputs
   - inspect sizes and validation
   - rerun Stage B without repeating normalization

Current HTTP split:

- Stage A: `/api/stage-a/import`, `/api/stage-a/local-file`, `/api/stage-a/upload`
- Stage B: `/api/stage-b/generate`
- Inventory: `/api/datasets` returns both generated datasets and normalized bundle inventory (`normalized`).

Current UI split (`MapsList`):

- section "Stage A: Normalize Source"
- section "Stage B: Generate MVT/MLT" (from normalized bundles)

The protocol distinguishes raw source, normalized GPKG, and tile outputs. Heavy jobs stay serialized by default so timing and resource metrics remain comparable.

## Dense Variant Contract

| Variant | Detail offset | Extent |
|---|---:|---:|
| `standard` | 0 | 4096 |
| `dense4` | 1 | 8192 |
| `dense16` | 2 | 16384 |

Layer zoom requests are shifted by the detail offset. Dataset-level GDAL zoom envelopes are computed so no shifted layer request is outside the produced archive.

## Technology Stack

| Component | Technology |
|---|---|
| API/converter | Python, GDAL/OGR, pmtiles Python reader/writer |
| MVT codec | `mapbox-vector-tile` |
| MLT codec | `maplibre-tiles` |
| Web | React, Vite, MapLibre GL JS, pmtiles JS |
| Container | PMTiles v3 |

MBTiles is used only as an intermediate GDAL container before PMTiles repacking.
The published code excludes Planetiler and the separate traffic study.

## Stage B Timing Model

Stage B now reports only the active timing model, without legacy compatibility aliases:

- `gpkg_preflight`
- `mvt_generation`
- `mvt_scan`
- `mvt_to_mlt`
- `mlt_validation`
- `total_postprocessing`
