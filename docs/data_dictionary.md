# Data dictionary and counting rules

## Read these rules first

1. Tile summaries are **address-weighted**: a shared payload contributes once per
   z/x/y address. MLT layer/stream tables are **payload-weighted**: a stored payload
   is parsed once. Do not join streams to addresses and sum without deciding which
   weighting you intend.
2. `attribute_type_profiles` is per payload pair, layer, property and original
   MVT type. `absent_count` describes the property, repeated across original-type
   rows: **never sum it across those rows**.
3. `attribute_transitions.value_occurrences` and summary totals already include
   address multiplicity. **Do not multiply by `address_count` again.**
4. Strict equality is diagnostic. It compares typed values, IDs, extents and
   geometry multisets, and may detect more than type coercion. A successful
   pair comparison does not prove source-feature completeness.
5. `stored_bytes` means the original PMTiles payload length. `raw_payload_bytes`
   means decompressed length. `gzip_payload_bytes` is recomputed with gzip level 6,
   `mtime=0`. These are different measurements; equal lengths do not prove equal
   streams or identify original encoder settings.

## Database grains and relationships

| Database/table family | One row represents | Keys / interpretation |
|---|---|---|
| source/normalized `maps`, `components` | Selected source file / archive member | `mapName`, component index; source rows, never tile instances |
| source/normalized `layers`, `geometry_types` | Source layer / geometry kind | `mapName`, `layerName`; unavailable geometry counts are NULL |
| `layer_fields`, `field_values` | Layer field / profiled categorical value | Values may be capped; inspect cardinality flags |
| `semantic_types`, `semantic_metadata` | Classified feature/attribute category | Classifier evidence; not ground truth |
| `zoom_stats`, `zoom_layers` | Observed zoom / layer at zoom | Empty for non-tiled vector sources |
| `raster_bands`, `raster_values` | Raster band / value | Inherited analyzer schema; empty in this vector-only study |
| `dataset_files` | Corpus ID to measured filename | `dataset_id`; stage is raw or normalized |
| tile `maps`, `archives` | Dataset variant / physical archive | `archives.map_id → maps.id`; format MVT or MLT |
| `tiles` | Archive z/x/y | Shared payloads can occur at several addresses |
| `tile_content_stats`, `tile_layer_stats`, `tile_layers` | Decoded tile / tile layer | Content is measured from MVT; tile instances include clipping duplication |
| `mlt_layers`, `mlt_streams` | Unique payload layer/frame / stream | Archive ID + content offset + layer/stream indices |
| tile `layers`, `properties`, `property_values` | Layer/property/value summary | Capped distinct values are lower bounds when the cap is exceeded |
| `pair_validation` | Variant archive pair | Coordinate-set check, not full object equality |
| `gzip_check`, `parser_checks`, `parse_diagnostics` | Archive or variant diagnostics | Length checks and frame accounting |
| `bounds`, `bounds_checks`, `study_area` | Dataset stage bounds / comparison | WGS84 degrees; area in km²; unknown checks are not passes |
| `validation`, `validation_issues` | Full decoded pair check / capped example | Aggregate mismatch counts are complete; issue samples are capped |
| `attribute_payload_pairs` | Unique paired payload locations | `pair_id`; `address_count` counts reuse |
| `attribute_tile_addresses` | Payload pair z/x/y | `pair_id → attribute_payload_pairs.pair_id` |
| `attribute_type_profiles` | Payload pair/layer/property/before type | MLT column declaration, not matched-object values |
| `attribute_transitions`, `attribute_type_summary` | Address-weighted type transition / dataset variant | Already weighted totals |
| `attribute_type_errors`, `analysis_errors` | Recorded failure | Empty means no recorded failures, not proof of independent verification |
| results summary tables | Group of measured addresses or streams | Exact grouping and expressions are in `analysis/sql/00_*.sql`–`18_*.sql` |
| `meta`, `analysis_meta` | Key/value metadata / analyzer run | Environment, fingerprints, schema versions |

## Columns, units and missing values

The [schema catalogue](schema.md) enumerates every table and column in the measured
corpus. The release's `schema.json` is generated from its actual databases and
adds Parquet types and row counts. SQL expressions are the authoritative definitions
of derived metrics; `analysis/pipeline.py` defines source structure and extra checks.

| Column / family | Meaning and units | NULL means |
|---|---|---|
| `dataset_id`, `dataset_name`, `mapName`, `layer_name`, `layerName` | Corpus, filename and layer identities; strings | Identity unavailable / no corresponding layer |
| `variant`, `density_factor` | standard/1, dense4/4, dense16/16 | Unclassified variant |
| `z`, `x`, `y`, `zoom`, `min_zoom`, `max_zoom` | Stored XYZ Web Mercator address or zoom; dimensionless | Not available / not applicable |
| `logical_z`, `logical_zoom` | Stored zoom + 0/1/2 for Standard/Dense-4/Dense-16 | Logical zoom unavailable |
| `extent` | Integer coordinate-grid extent: 4096/8192/16384 | Missing metadata |
| `*_bytes`, `fileBytes`, `payloadBytes`, `storedBytes` | Byte lengths; frame/header/payload names identify scope | Measurement unavailable / parse failed |
| `*_kib`, `*_mib` | KiB = 1024 bytes; MiB = 1048576 bytes | Measurement unavailable |
| `feature_instances`, `features`, `vertex_count`, `vertices` | Counts at the table's grain; source rows versus tile instances as above | Unmeasured; never silently zero |
| `*_saving_pct` | 100 × (1 − compared-byte sum / baseline-byte sum); may be negative | Missing inputs or zero denominator |
| `g_raw`, `g_gz`, `delta_pp`, `g_gzip9`, `g_brotli11`, `g_zstd19` | Dense savings minus Standard savings; percentage points | No matching Standard group / zero denominator |
| `bytes_per_vertex.*`, `*_bytes_per_vertex` | Bytes per vertex; ratio of sums | Missing/zero vertex denominator |
| `values_per_stream` | Total stream values / total streams | Zero/missing stream denominator |
| `r_struct` | (MLT frame bytes − stream payload bytes) / frame bytes; fraction | Zero/missing frame denominator |
| `stream_header_share` | Stream header bytes / total stream bytes; fraction | Zero/missing denominator |
| `payload_bytes_per_value`, `bytes_per_value` | Payload or total stream bytes per value, respectively | Zero/missing value denominator |
| `spearman_rho` | Rank correlation of tile saving and predictor, −1 to +1 | Too few values or constant variable |
| `before_type`, `after_type`, `after_storage` | MVT protobuf type, MLT declared column type/storage | Missing or unrecognized column |
| `after_nullable` | Whether MLT metadata permits NULL: 0/1 | Missing declaration; does not count actual NULL values |
| `value_count`, `absent_count` | Present typed values / absent properties per payload; see non-additivity rule | Unmeasured |
| `value_occurrences`, `*_tile_occurrences` | Address-weighted counts | Unmeasured |
| `bounds_ok`, `passed`, `same_tile_coordinates` | Boolean result, 0/1 | Unknown / not checked |
| `status`, `method`, `mode`, `weighting` | Explicit measurement/check method or outcome | Not recorded |
| `*_json` | UTF-8 JSON; samples may contain real source attributes | No recorded value/sample |
| `min_lon`, `max_lon`, `min_lat`, `max_lat`, `*_excess`, `tolerance_degrees` | WGS84 degrees | Missing reference or extent |
| `area_km2`, `*AreaKm2` | Geodesic or tile area as named; km² | No usable bounds |
| `elapsed_seconds` | Wall-clock duration in seconds | Not measured |
| `*_at_utc`, `generatedAt` | UTC timestamp text | Not recorded |

All other NULLs mean unavailable, inapplicable, a failed measurement, or a derived
zero-denominator result; consult the same row's status/error. They never mean a
measured zero. Empty tables retain schema and do not imply measured zero values.
SQLite declarations permit NULL even where a particular build contains none.
