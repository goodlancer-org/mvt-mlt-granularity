# Canonical Object Taxonomy

GEOMAPS normalizes heterogeneous vector source schemas into a stable semantic taxonomy before tiling. The active taxonomy is vector-only.

## Canonical Semantic Kinds

- `water`
- `land`
- `boundary`
- `transport`
- `place`
- `building`
- `infrastructure`
- `terrain`
- `unknown`

`raster` is not an active GEOMAPS semantic kind. Raster tile formats are still discussed in the separate real-world web-map traffic study as observed external traffic, not as supported project inputs.

## Where Normalization Happens

Stage A materializes semantic normalization in the canonical GPKG and its manifest:

- raw source layer names become stable normalized source-layer names
- CRS, bounds selection with physical clipping, identity strategy, and provenance are fixed
- output geometry is canonical XY-only `EPSG:3857` with required spatial indexes
- `makevalid` is opt-in via normalization profile rules
- field/class normalization needed for common rendering is recorded
- source provenance is retained so every normalized layer can be traced back
- cache fingerprint tracks normalization rules only (tile zoom/layer grouping rules are Stage B concerns)

Stage B consumes those normalized source layers and may group them differently into output MVT layers without rebuilding the GPKG.

```text
raw source layer -> normalized source layer -> output MVT tile layer
```

For standalone Stage-B runs, source identity is recovered from the normalization manifest (`source_type`, `source_filename`) so profile rules remain tied to the original dataset type.

## Type Inventory

`docs/object_type_inventory.json` is the generated inventory used to audit active vector datasets. It contains only vector corpus members. Regenerate it from the analysis database when source profiles change, then filter out non-vector datasets before treating it as active documentation.

## Mapping Rules

Rules live in:

- `app/converter/profiles/profile_rules.yaml`
- `app/converter/src/profile_rules.py`
- `app/converter/src/semantic_taxonomy.py`

The UI style engine should consume normalized `semantic_kind` metadata first and use name heuristics only as a fallback.

## Rendering Contract

- `water`: blue fills/lines
- `land`: stable land-use tones
- `boundary`: neutral outlines
- `transport`: high-contrast route lines
- `place`: points and labels
- `building`: urban footprint styling
- `infrastructure`: utility/structure styling
- `terrain`: subdued geology/relief palette
- `unknown`: visible fallback plus audit signal

## Governance

1. Regenerate the inventory.
2. Review unknown or high-frequency unmapped values.
3. Update profile rules and taxonomy mapping.
4. Re-normalize affected datasets when Stage A rules changed.
5. Regenerate Stage B PMTiles when only tile grouping or zoom rules changed.
