# GEOMAPS Vector Corpus

This is the active corpus inventory for the current GEOMAPS research pipeline. The active project is vector-only: raw vector sources are normalized once into canonical GeoPackages, and PMTiles outputs are generated from those normalized artifacts.

Raster formats may still appear in `docs/real-world-map-traffic*.md` because that study observes external web-map traffic. They are not supported GEOMAPS input formats for this pipeline.

## Artifact Classes

| Class | Example | Research role |
|---|---|---|
| Raw vector source | OSM PBF, CityGML/GML, Shapefile/Interlis, GeoPackage | source evidence and provenance |
| Normalized GPKG | `/data/normalized/<dataset>/<dataset>.gpkg` | reusable canonical source for Stage B |
| Normalization manifest | `<dataset>.normalization.json` | schema version, normalization-only fingerprint, CRS, bounds/clip mode, layer counts, stable-ID strategy, original source identity |
| MVT PMTiles | `standard_mvt`, `dense4_mvt`, `dense16_mvt` | measured row-oriented vector-tile encodings |
| MLT PMTiles | paired `*_mlt` archives | column-oriented transcodes of the matching MVT archives |

Intermediate GeoPackages, logs, manifests, and scratch files are provenance/supporting artifacts. Only the generated PMTiles archives count as measured compression outputs.

## Active Sources

| Dataset | Raw vector source | Normalization focus |
|---|---|---|
| Louisiana OSM | `louisiana-260912.osm.pbf` | OSM layer/tag normalization, unknown source counts, building/transport grouping |
| USFWS Louisiana wetlands | GeoPackage ZIP | `NWI_ID` identity preservation and wetland class retention |
| Natural Earth | GeoPackage ZIP | multi-scale layer preservation and canonical physical-map grouping |
| PDOK Netherlands infrastructure | GML / CityGML ZIP | CRS handling, many source layers, dense infrastructure semantics |
| Swisstopo mountains | Shapefile / Interlis ZIP | geology/terrain classification and line/polygon hierarchy |

## Research Invariants

For every variant pair:

- `set(variant_mvt z/x/y) == set(variant_mlt z/x/y)`
- layer names match
- feature counts match
- feature IDs and attributes are preserved where present
- geometry matches under the project comparison rules
- vertex counts across Standard/Dense variants are measured statistically, not forced equal, because clipping boundaries differ

For every normalized source:

- the GPKG and manifest can be shared without the original raw source
- bounds, clipping, CRS, semantic normalization, and stable identity are fixed in Stage A
- Stage A writes XY-only `EPSG:3857` GPKG with spatial indexes; `makevalid` is opt-in by profile rule
- tile-layer grouping and zoom rules remain Stage B concerns

For every Stage B run:

- canonical GPKG input is used as-is (no repeated spatial filtering or reprojection)
- per-variant MVT tiles are generated via GDAL MVT driver to MBTiles, then repacked to PMTiles
- standalone Stage-B runs recover original source identity from the normalization manifest

## Dense Products

| Product pair | Meaning |
|---|---|
| `standard_mvt` / `standard_mlt` | normal WebMercator pyramid, extent 4096 |
| `dense4_mvt` / `dense4_mlt` | stored `z` carries Standard `z+1` detail, extent 8192 |
| `dense16_mvt` / `dense16_mlt` | stored `z` carries Standard `z+2` detail, extent 16384 |

The Standard pair is the primary preview target in the UI. Dense-4 and Dense-16 are compression-study artifacts.
