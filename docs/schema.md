# Schema catalogue

Catalogue of five SQLite schemas and the Parquet tile-measurement schema. This contains no source rows.
[Read the counting rules and NULL semantics first](data_dictionary.md).
Column descriptions use their table context. Counts inherit the table’s grain;
derived formulas and groupings are defined by the linked implementation.
The exported schema.json records the actual release schema and row counts.

## results.sqlite

### analysis_errors

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `id` | INT | Id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `map_id` | INT | Map id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `archive_format` | TEXT | Archive format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `z` | INT | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `x` | INT | Stored XYZ tile column at zoom z | tile index | unavailable / inapplicable; see status/error |
| `y` | INT | Stored XYZ tile row at zoom z | tile index | unavailable / inapplicable; see status/error |
| `message` | TEXT | Message; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### archive_totals

Definition and row grouping: [17_paper_metrics.sql](../analysis/sql/17_paper_metrics.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `gzip6_bytes` | expression affinity | Gzip6 bytes | bytes | unavailable / inapplicable; see status/error |
| `change_vs_standard_pct` | expression affinity | Change vs standard pct | percent | unavailable / inapplicable; see status/error |
| `weighting` | expression affinity | Recorded aggregation convention, address_weighted or payload grain | label | unavailable / inapplicable; see status/error |

### attribute_payload_pairs

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INT | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `mvt_offset` | INT | Mvt offset | bytes | unavailable / inapplicable; see status/error |
| `mvt_length` | INT | Mvt length | bytes | unavailable / inapplicable; see status/error |
| `mlt_offset` | INT | Mlt offset | bytes | unavailable / inapplicable; see status/error |
| `mlt_length` | INT | Mlt length | bytes | unavailable / inapplicable; see status/error |
| `address_count` | INT | Number of tile addresses reusing this payload pair | count | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### attribute_tile_addresses

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INT | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `z` | INT | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `x` | INT | Stored XYZ tile column at zoom z | tile index | unavailable / inapplicable; see status/error |
| `y` | INT | Stored XYZ tile row at zoom z | tile index | unavailable / inapplicable; see status/error |

### attribute_transitions

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `property_name` | TEXT | Property name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `before_type` | TEXT | MVT protobuf Value type before transcoding | type label | unavailable / inapplicable; see status/error |
| `after_type` | TEXT | MLT declared column type after transcoding | type label | unavailable / inapplicable; see status/error |
| `after_nullable` | INT | MLT declared column permits NULL; does not measure actual NULL count | 0/1 | unavailable / inapplicable; see status/error |
| `after_storage` | TEXT | After storage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `transition` | TEXT | Transition; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `column_type_tile_occurrences` | expression affinity | Column type tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_occurrences` | expression affinity | Present property values, already weighted by tile-address multiplicity | count | unavailable / inapplicable; see status/error |
| `mixed_source_value_occurrences` | expression affinity | Mixed source value occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### attribute_type_errors

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INT | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `message` | TEXT | Message; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### attribute_type_profiles

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INT | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `property_name` | TEXT | Property name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `before_type` | TEXT | MVT protobuf Value type before transcoding | type label | unavailable / inapplicable; see status/error |
| `after_type` | TEXT | MLT declared column type after transcoding | type label | unavailable / inapplicable; see status/error |
| `after_nullable` | INT | MLT declared column permits NULL; does not measure actual NULL count | 0/1 | unavailable / inapplicable; see status/error |
| `after_storage` | TEXT | After storage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value_count` | INT | Value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_features` | INT | Mvt features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `absent_count` | INT | Missing property count per payload; repeated across original-type rows, not additive | count | unavailable / inapplicable; see status/error |
| `source_type_count` | INT | Source type count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `transition` | TEXT | Transition; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `before_examples_json` | TEXT | Sample original attribute values; upstream source terms apply | JSON | unavailable / inapplicable; see status/error |

### attribute_type_summary

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `property_tile_occurrences` | expression affinity | Property tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mixed_property_tile_occurrences` | expression affinity | Mixed property tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_occurrences` | expression affinity | Present property values, already weighted by tile-address multiplicity | count | unavailable / inapplicable; see status/error |
| `to_string_value_occurrences` | expression affinity | To string value occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `missing_column_tile_occurrences` | expression affinity | Missing column tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_only_column_tile_occurrences` | expression affinity | Mlt only column tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### bounds

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `id` | INT | Id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `stage` | TEXT | Stage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `kind` | TEXT | Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `component` | TEXT | Component; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `zoom` | INT | Zoom | zoom level | unavailable / inapplicable; see status/error |
| `min_lon` | REAL | Min lon | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `min_lat` | REAL | Min lat | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `max_lon` | REAL | Max lon | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `max_lat` | REAL | Max lat | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `native_crs` | TEXT | Native crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `native_bounds_json` | TEXT | Native bounds json; serialized JSON metadata or sample | JSON | unavailable / inapplicable; see status/error |
| `path` | TEXT | Path; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sha256` | TEXT | Sha256; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `method` | TEXT | Method; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `details_json` | TEXT | Details json; serialized JSON metadata or sample | JSON | unavailable / inapplicable; see status/error |

### bounds_checks

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `zoom` | INT | Zoom | zoom level | unavailable / inapplicable; see status/error |
| `check_name` | TEXT | Check name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tolerance_degrees` | REAL | Tolerance degrees | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `west_excess` | REAL | West excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `south_excess` | REAL | South excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `east_excess` | REAL | East excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `north_excess` | REAL | North excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `message` | TEXT | Message; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### bytes_per_vertex

Definition and row grouping: [17_paper_metrics.sql](../analysis/sql/17_paper_metrics.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `vertices` | expression affinity | Vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_raw` | expression affinity | Mvt raw; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `mlt_raw` | expression affinity | Mlt raw; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `mvt_gzip6` | expression affinity | Mvt gzip6; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `mlt_gzip6` | expression affinity | Mlt gzip6; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |

### dense_gain

Definition and row grouping: [02_dense_gain.sql](../analysis/sql/02_dense_gain.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `standard_raw_pct` | expression affinity | Standard raw pct | percent | unavailable / inapplicable; see status/error |
| `dense4_raw_pct` | expression affinity | Dense4 raw pct | percent | unavailable / inapplicable; see status/error |
| `dense16_raw_pct` | expression affinity | Dense16 raw pct | percent | unavailable / inapplicable; see status/error |
| `standard_after_gzip_pct` | expression affinity | Standard after gzip pct | percent | unavailable / inapplicable; see status/error |
| `dense4_after_gzip_pct` | expression affinity | Dense4 after gzip pct | percent | unavailable / inapplicable; see status/error |
| `dense16_after_gzip_pct` | expression affinity | Dense16 after gzip pct | percent | unavailable / inapplicable; see status/error |

### feature_binned

Definition and row grouping: [03_feature_binned.sql](../analysis/sql/03_feature_binned.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `feature_bin` | expression affinity | Feature bin; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `feature_instances` | expression affinity | Feature instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertex_count` | expression affinity | Vertex count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `layer_count` | expression affinity | Layer count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_raw_bytes` | INT | Mvt raw bytes | bytes | unavailable / inapplicable; see status/error |
| `mvt_gzip_bytes` | INT | Mvt gzip bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_raw_bytes` | INT | Mlt raw bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_gzip_bytes` | INT | Mlt gzip bytes | bytes | unavailable / inapplicable; see status/error |

### feature_summary

Definition and row grouping: [04_feature_summary.sql](../analysis/sql/04_feature_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `feature_bin` | expression affinity | Feature bin; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_features` | expression affinity | Avg features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_vertices` | expression affinity | Avg vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_layers` | expression affinity | Avg layers at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_mvt_raw_kib` | expression affinity | Avg mvt raw kib | KiB (2¹⁰ bytes) | unavailable / inapplicable; see status/error |
| `mvt_gzip_saving_pct` | expression affinity | Mvt gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_after_gzip_saving_pct` | expression affinity | Mlt after gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |

### geometry_summary

Definition and row grouping: [09_geometry_summary.sql](../analysis/sql/09_geometry_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `geometry_type` | TEXT | Geometry type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `feature_count` | expression affinity | Feature count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertex_count` | expression affinity | Vertex count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertices_per_feature` | expression affinity | Vertices per feature at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### granularity_gain

Definition and row grouping: [17_paper_metrics.sql](../analysis/sql/17_paper_metrics.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `g_raw` | expression affinity | Raw MLT saving minus Standard raw MLT saving | percentage points | unavailable / inapplicable; see status/error |
| `g_gz` | expression affinity | Gzip-6 MLT saving minus Standard gzip-6 MLT saving | percentage points | unavailable / inapplicable; see status/error |
| `weighting` | expression affinity | Recorded aggregation convention, address_weighted or payload grain | label | unavailable / inapplicable; see status/error |

### gzip_check

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `n_tiles` | expression affinity | N tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `n_equal` | expression affinity | N equal; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sum_stored` | expression affinity | Sum stored; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sum_gzip6` | expression affinity | Sum gzip6; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `max_abs_diff` | expression affinity | Max abs diff; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### gzip_impact

Definition and row grouping: [18_gzip_impact.sql](../analysis/sql/18_gzip_impact.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `stored_saving_pct` | expression affinity | Stored saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `gzip6_saving_pct` | expression affinity | Gzip6 saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `delta_pp` | expression affinity | Delta pp; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `weighting` | expression affinity | Recorded aggregation convention, address_weighted or payload grain | label | unavailable / inapplicable; see status/error |

### layer_compression

Definition and row grouping: [08_layer_compression.sql](../analysis/sql/08_layer_compression.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `feature_count` | expression affinity | Feature count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertex_count` | expression affinity | Vertex count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_raw_mib` | expression affinity | Mvt raw mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `mlt_raw_mib` | expression affinity | Mlt raw mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mvt_key_count` | expression affinity | Mvt key count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_value_count` | expression affinity | Mvt value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_stream_count` | expression affinity | Mlt stream count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `stream_payload_mib` | expression affinity | Stream payload mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `stream_overhead_mib` | expression affinity | Stream overhead mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `stream_overhead_pct` | expression affinity | Stream overhead pct | percent | unavailable / inapplicable; see status/error |
| `parse_error_count` | expression affinity | Parse error count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### layer_count_summary

Definition and row grouping: [07_layer_count_summary.sql](../analysis/sql/07_layer_count_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `layer_count` | expression affinity | Layer count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_features` | expression affinity | Avg features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_vertices` | expression affinity | Avg vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_after_gzip_saving_pct` | expression affinity | Mlt after gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |

### layer_mapping

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `source_layer` | TEXT | Source layer; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tile_layer` | TEXT | Tile layer; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `features` | INT | Features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertices` | INT | Vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fields` | INT | Fields at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### layer_parse_coverage

Definition and row grouping: [15_layer_parse_coverage.sql](../analysis/sql/15_layer_parse_coverage.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `layer_frames` | expression affinity | Layer frames at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `failed_frames` | expression affinity | Failed frames at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `frame_bytes` | expression affinity | Frame bytes | bytes | unavailable / inapplicable; see status/error |
| `failed_frame_bytes` | expression affinity | Failed frame bytes | bytes | unavailable / inapplicable; see status/error |

### logical_zoom_summary

Definition and row grouping: [16_logical_zoom_summary.sql](../analysis/sql/16_logical_zoom_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `logical_z` | expression affinity | Stored zoom plus detail offset 0/1/2 | zoom level | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_vertices_per_tile` | expression affinity | Avg vertices per tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_raw_bytes` | expression affinity | Mvt raw bytes | bytes | unavailable / inapplicable; see status/error |
| `mvt_gzip_bytes` | expression affinity | Mvt gzip bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_raw_bytes` | expression affinity | Mlt raw bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_gzip_bytes` | expression affinity | Mlt gzip bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_after_gzip_saving_pct` | expression affinity | Mlt after gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |

### meta

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `key` | TEXT (PK) | Key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `value` | TEXT | Metadata or profiled source value; interpretation depends on key/table | text or source units | not permitted |

### mlt_stream_layer_summary

Definition and row grouping: [11_mlt_stream_layer_summary.sql](../analysis/sql/11_mlt_stream_layer_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stream_role` | TEXT | Stream role; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `logical_encoding` | TEXT | Logical encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `physical_encoding` | TEXT | Physical encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stream_count` | expression affinity | Stream count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_count` | expression affinity | Value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `total_kib` | expression affinity | Total kib | KiB (2¹⁰ bytes) | unavailable / inapplicable; see status/error |
| `bytes_per_value` | expression affinity | Bytes per value | bytes/value | unavailable / inapplicable; see status/error |

### mlt_stream_summary

Definition and row grouping: [10_mlt_stream_summary.sql](../analysis/sql/10_mlt_stream_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `stream_role` | TEXT | Stream role; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `logical_encoding` | TEXT | Logical encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `physical_encoding` | TEXT | Physical encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stream_count` | expression affinity | Stream count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_count` | expression affinity | Value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `payload_mib` | expression affinity | Payload mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `header_mib` | expression affinity | Header mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `total_mib` | expression affinity | Total mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `avg_values_per_stream` | expression affinity | Avg values per stream at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `bytes_per_value` | expression affinity | Bytes per value | bytes/value | unavailable / inapplicable; see status/error |
| `header_overhead_pct` | expression affinity | Header overhead pct | percent | unavailable / inapplicable; see status/error |

### normalized_structure

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `sourceFormat` | TEXT | Source Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fileBytes` | INT | File Bytes | bytes | unavailable / inapplicable; see status/error |
| `layers` | expression affinity | Layers at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `features` | expression affinity | Features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertices` | expression affinity | Vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fields` | expression affinity | Fields at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `distinct_fields` | expression affinity | Distinct fields at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `errorCount` | INT | Error Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### pair_validation

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INT | Map id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `mvt_tile_count` | INT | Mvt tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_tile_count` | INT | Mlt tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `missing_in_mlt` | INT | Missing in mlt; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `missing_in_mvt` | INT | Missing in mvt; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `same_tile_coordinates` | INT | Same tile coordinates; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### parse_diagnostics

Definition and row grouping: [12_parse_diagnostics.sql](../analysis/sql/12_parse_diagnostics.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `frame_tag` | INT | Frame tag; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `parse_error` | TEXT | Parse error; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |
| `occurrence_count` | expression affinity | Occurrence count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### parser_checks

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INT | Map id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `archive_id` | INT | Archive id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `layer_frames` | expression affinity | Layer frames at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `failed_frames` | expression affinity | Failed frames at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `frame_bytes` | expression affinity | Frame bytes | bytes | unavailable / inapplicable; see status/error |
| `stream_bytes` | expression affinity | Stream bytes | bytes | unavailable / inapplicable; see status/error |

### raw_structure

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `sourceFormat` | TEXT | Source Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fileBytes` | INT | File Bytes | bytes | unavailable / inapplicable; see status/error |
| `layers` | expression affinity | Layers at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `features` | expression affinity | Features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertices` | expression affinity | Vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fields` | expression affinity | Fields at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `distinct_fields` | expression affinity | Distinct fields at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `errorCount` | INT | Error Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### stream_summary

Definition and row grouping: [17_paper_metrics.sql](../analysis/sql/17_paper_metrics.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `stream_count` | expression affinity | Stream count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_count` | expression affinity | Value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `header_bytes` | expression affinity | Header bytes | bytes | unavailable / inapplicable; see status/error |
| `payload_bytes` | expression affinity | Payload bytes | bytes | unavailable / inapplicable; see status/error |
| `stream_bytes` | expression affinity | Stream bytes | bytes | unavailable / inapplicable; see status/error |
| `values_per_stream` | expression affinity | Values per stream at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `stream_header_share` | expression affinity | Stream headers divided by total stream bytes | fraction | unavailable / inapplicable; see status/error |
| `payload_bytes_per_value` | expression affinity | Payload bytes per value | bytes/value | unavailable / inapplicable; see status/error |
| `r_struct` | expression affinity | Fraction of MLT frame bytes outside stream payloads | fraction | unavailable / inapplicable; see status/error |
| `weighting` | expression affinity | Recorded aggregation convention, address_weighted or payload grain | label | unavailable / inapplicable; see status/error |

### stream_totals

Definition and row grouping: [14_stream_totals.sql](../analysis/sql/14_stream_totals.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `stream_count` | expression affinity | Stream count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_count` | expression affinity | Value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `header_bytes` | expression affinity | Header bytes | bytes | unavailable / inapplicable; see status/error |
| `payload_bytes` | expression affinity | Payload bytes | bytes | unavailable / inapplicable; see status/error |
| `stream_bytes` | expression affinity | Stream bytes | bytes | unavailable / inapplicable; see status/error |

### study_area

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `declared_bounds` | TEXT | Declared bounds; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `actual_extent` | TEXT | Actual extent; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `area_km2` | REAL | Area km2 | km² | unavailable / inapplicable; see status/error |
| `bounds_ok` | INT | Declared bounds contain the measured normalized extent | 0/1 | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### tile_correlation

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `measure` | TEXT | Measure; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `predictor` | TEXT | Predictor; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `n_tiles` | INTEGER | N tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `spearman_rho` | REAL | Rank correlation between tile saving and the named predictor | coefficient [-1,1] | unavailable / inapplicable; see status/error |
| `weighting` | TEXT | Recorded aggregation convention, address_weighted or payload grain | label | unavailable / inapplicable; see status/error |

### validation

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `mode` | TEXT | Mode; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_path` | TEXT | Mvt path; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mlt_path` | TEXT | Mlt path; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_sha256` | TEXT | Mvt sha256; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mlt_sha256` | TEXT | Mlt sha256; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_tiles` | INT | Mvt tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_tiles` | INT | Mlt tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `checked_tiles` | INT | Checked tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mismatches` | INT | Mismatches at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `errors` | INT | Errors at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `missing_mvt` | INT | Missing mvt; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `missing_mlt` | INT | Missing mlt; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `passed` | INT | Strict comparison pass flag; diagnostic, not an acceptance gate | 0/1 | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `elapsed_seconds` | REAL | Elapsed seconds | seconds | unavailable / inapplicable; see status/error |
| `validated_at_utc` | TEXT | Validated at utc | UTC timestamp | unavailable / inapplicable; see status/error |

### validation_issues

Definition and row grouping: [pipeline.py](../analysis/pipeline.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `z` | INT | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `x` | INT | Stored XYZ tile column at zoom z | tile index | unavailable / inapplicable; see status/error |
| `y` | INT | Stored XYZ tile row at zoom z | tile index | unavailable / inapplicable; see status/error |
| `category` | TEXT | Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `details_json` | TEXT | Details json; serialized JSON metadata or sample | JSON | unavailable / inapplicable; see status/error |

### variant_compression

Definition and row grouping: [01_variant_compression.sql](../analysis/sql/01_variant_compression.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `raw_saving_pct` | expression affinity | Raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `after_gzip_saving_pct` | expression affinity | After gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |

### variant_summary

Definition and row grouping: [00_variant_summary.sql](../analysis/sql/00_variant_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `density_factor` | INT | Nominal represented tile-area factor: 1, 4 or 16 | factor | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `feature_count` | expression affinity | Feature count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertex_count` | expression affinity | Vertex count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_features_per_tile` | expression affinity | Avg features per tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_vertices_per_tile` | expression affinity | Avg vertices per tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_layers_per_tile` | expression affinity | Avg layers per tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_raw_mib` | expression affinity | Mvt raw mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `mvt_gzip_mib` | expression affinity | Mvt gzip mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `mlt_raw_mib` | expression affinity | Mlt raw mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `mlt_gzip_mib` | expression affinity | Mlt gzip mib | MiB (2²⁰ bytes) | unavailable / inapplicable; see status/error |
| `mvt_gzip_saving_pct` | expression affinity | Mvt gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_after_gzip_saving_pct` | expression affinity | Mlt after gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `total_mlt_gzip_saving_pct` | expression affinity | Total mlt gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mvt_raw_bytes_per_feature` | expression affinity | Mvt raw bytes per feature | bytes | unavailable / inapplicable; see status/error |
| `mlt_raw_bytes_per_feature` | expression affinity | Mlt raw bytes per feature | bytes | unavailable / inapplicable; see status/error |
| `mvt_raw_bytes_per_vertex` | expression affinity | Mvt raw bytes per vertex; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `mlt_raw_bytes_per_vertex` | expression affinity | Mlt raw bytes per vertex; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `mvt_gzip_bytes_per_vertex` | expression affinity | Mvt gzip bytes per vertex; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `mlt_gzip_bytes_per_vertex` | expression affinity | Mlt gzip bytes per vertex; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |

### vertex_binned

Definition and row grouping: [05_vertex_binned.sql](../analysis/sql/05_vertex_binned.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `vertex_bin` | expression affinity | Vertex bin; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `feature_instances` | expression affinity | Feature instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertex_count` | expression affinity | Vertex count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `layer_count` | expression affinity | Layer count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_raw_bytes` | INT | Mvt raw bytes | bytes | unavailable / inapplicable; see status/error |
| `mvt_gzip_bytes` | INT | Mvt gzip bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_raw_bytes` | INT | Mlt raw bytes | bytes | unavailable / inapplicable; see status/error |
| `mlt_gzip_bytes` | INT | Mlt gzip bytes | bytes | unavailable / inapplicable; see status/error |

### vertex_summary

Definition and row grouping: [06_vertex_summary.sql](../analysis/sql/06_vertex_summary.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `vertex_bin` | expression affinity | Vertex bin; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_vertices` | expression affinity | Avg vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_features` | expression affinity | Avg features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_layers` | expression affinity | Avg layers at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_mvt_raw_kib` | expression affinity | Avg mvt raw kib | KiB (2¹⁰ bytes) | unavailable / inapplicable; see status/error |
| `mvt_gzip_saving_pct` | expression affinity | Mvt gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_after_gzip_saving_pct` | expression affinity | Mlt after gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |

### vertex_summary_by_dataset

Definition and row grouping: [13_vertex_summary_by_dataset.sql](../analysis/sql/13_vertex_summary_by_dataset.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `vertex_bin` | expression affinity | Vertex bin; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tile_count` | expression affinity | Tile count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_vertices` | expression affinity | Avg vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `avg_features` | expression affinity | Avg features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_raw_saving_pct` | expression affinity | Mlt raw saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |
| `mlt_after_gzip_saving_pct` | expression affinity | Mlt after gzip saving pct; 100 × (1 − compared sum / baseline sum) | percent | unavailable / inapplicable; see status/error |

### zoom_comparison

Definition and row grouping: [17_paper_metrics.sql](../analysis/sql/17_paper_metrics.sql).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `logical_z` | expression affinity | Stored zoom plus detail offset 0/1/2 | zoom level | unavailable / inapplicable; see status/error |
| `delta_raw` | expression affinity | Delta raw; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `delta_gz` | expression affinity | Delta gz; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `raw_class` | expression affinity | Raw class; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `gz_class` | expression affinity | Gz class; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

## source_stats.sqlite

### analysis_errors

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stage` | VARCHAR | Stage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `errorType` | VARCHAR | Error Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `error` | VARCHAR | Recorded diagnostic error; NULL means no recorded error for this row | text | no recorded message/error |
| `traceback` | VARCHAR | Traceback; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### analysis_meta

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `schemaVersion` | INTEGER | Schema Version; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `analyzerVersion` | VARCHAR | Analyzer Version; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `generatedAt` | TEXT | Generated At | UTC timestamp | unavailable / inapplicable; see status/error |

### components

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentIndex` | INTEGER | Component Index; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `format` | VARCHAR | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fileBytes` | BIGINT | File Bytes | bytes | unavailable / inapplicable; see status/error |
| `tileEncoding` | VARCHAR | Tile Encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `crs` | VARCHAR | Crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `minZoom` | INTEGER | Min Zoom | zoom level | unavailable / inapplicable; see status/error |
| `maxZoom` | INTEGER | Max Zoom | zoom level | unavailable / inapplicable; see status/error |
| `structuralCount` | BIGINT | Structural Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `payloadBytes` | BIGINT | Payload Bytes | bytes | unavailable / inapplicable; see status/error |

### dataset_files

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT (PK) | Stable corpus identifier from analysis/datasets.json | identifier | not permitted |
| `map_name` | TEXT | Map name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stage` | TEXT | Stage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### field_values

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fieldName` | VARCHAR | Field Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | VARCHAR | Metadata or profiled source value; interpretation depends on key/table | text or source units | unavailable / inapplicable; see status/error |
| `valueType` | VARCHAR | Value Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `count` | BIGINT | Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fraction` | DOUBLE | Fraction; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### geometry_types

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceGeometryType` | VARCHAR | Source Geometry Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `analysisGeometryType` | VARCHAR | Analysis Geometry Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureCount` | BIGINT | Feature Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `linearized` | BOOLEAN | Linearized; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### layer_fields

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fieldName` | VARCHAR | Field Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `dataType` | VARCHAR | Data Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `populatedCount` | BIGINT | Populated Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `nullOrMissingCount` | BIGINT | Null Or Missing Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `distinctCount` | BIGINT | Distinct Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `distinctAtLeast` | BIGINT | Distinct At Least; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `cardinalityExceeded` | BOOLEAN | Cardinality Exceeded; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fieldRole` | VARCHAR | Field Role; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### layers

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `declaredGeometry` | VARCHAR | Declared Geometry; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureInstances` | BIGINT | Feature Instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `featuresWithId` | BIGINT | Features With Id at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fieldCount` | BIGINT | Field Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `minZoom` | INTEGER | Min Zoom | zoom level | unavailable / inapplicable; see status/error |
| `maxZoom` | INTEGER | Max Zoom | zoom level | unavailable / inapplicable; see status/error |
| `semanticCategory` | VARCHAR | Semantic Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticSource` | VARCHAR | Semantic Source; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticConfidence` | DOUBLE | Semantic Confidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticEvidence` | VARCHAR | Semantic Evidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `countMeaning` | VARCHAR | Explicit interpretation of source or tile feature counts | text | unavailable / inapplicable; see status/error |
| `geometryLinearized` | BOOLEAN | Geometry Linearized; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### maps

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceFormat` | VARCHAR | Source Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mapKind` | VARCHAR | Map Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tileEncoding` | VARCHAR | Tile Encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentCount` | BIGINT | Component Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fileBytes` | BIGINT | File Bytes | bytes | unavailable / inapplicable; see status/error |
| `crs` | VARCHAR | Crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `minZoom` | INTEGER | Min Zoom | zoom level | unavailable / inapplicable; see status/error |
| `maxZoom` | INTEGER | Max Zoom | zoom level | unavailable / inapplicable; see status/error |
| `title` | VARCHAR | Title; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `attribution` | VARCHAR | Attribution; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticCategory` | VARCHAR | Semantic Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticSource` | VARCHAR | Semantic Source; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticConfidence` | DOUBLE | Semantic Confidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `errorCount` | BIGINT | Error Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### meta

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `key` | TEXT (PK) | Key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `value` | TEXT | Metadata or profiled source value; interpretation depends on key/table | text or source units | not permitted |

### raster_bands

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentIndex` | INTEGER | Component Index; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `band` | INTEGER | Band; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `dataType` | VARCHAR | Data Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `width` | BIGINT | Width; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `height` | BIGINT | Height; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `validPixelCount` | BIGINT | Valid Pixel Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `noData` | DOUBLE | No Data; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `crs` | VARCHAR | Crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `resolutionX` | DOUBLE | Resolution X; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `resolutionY` | DOUBLE | Resolution Y; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `minimum` | DOUBLE | Minimum; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `maximum` | DOUBLE | Maximum; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mean` | DOUBLE | Mean; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stddev` | DOUBLE | Stddev; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `uniqueValueCount` | BIGINT | Unique Value Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `valueMode` | VARCHAR | Value Mode; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `unit` | VARCHAR | Unit; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticCategory` | VARCHAR | Semantic Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### raster_values

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentIndex` | INTEGER | Component Index; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `band` | INTEGER | Band; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | VARCHAR | Metadata or profiled source value; interpretation depends on key/table | text or source units | unavailable / inapplicable; see status/error |
| `valueType` | VARCHAR | Value Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `pixelCount` | BIGINT | Pixel Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fraction` | DOUBLE | Fraction; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### semantic_metadata

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `key` | VARCHAR | Key; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | VARCHAR | Metadata or profiled source value; interpretation depends on key/table | text or source units | unavailable / inapplicable; see status/error |
| `sourceKind` | VARCHAR | Source Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### semantic_types

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceType` | VARCHAR | Source Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceField` | VARCHAR | Source Field; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceValue` | VARCHAR | Source Value; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `normalizedCategory` | VARCHAR | Normalized Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `normalizedType` | VARCHAR | Normalized Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceKind` | VARCHAR | Source Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `confidence` | DOUBLE | Confidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureCount` | BIGINT | Feature Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### zoom_layers

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tileAppearances` | BIGINT | Tile Appearances; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureInstances` | BIGINT | Feature Instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `meanFeaturesPerTile` | DOUBLE | Mean Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `medianFeaturesPerTile` | DOUBLE | Median Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p95FeaturesPerTile` | DOUBLE | P95Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### zoom_stats

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `tileCount` | BIGINT | Tile Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `featureInstances` | BIGINT | Feature Instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `storedBytes` | BIGINT | Stored Bytes | bytes | unavailable / inapplicable; see status/error |
| `decodedBytes` | BIGINT | Decoded Bytes | bytes | unavailable / inapplicable; see status/error |
| `tileCoverageAreaKm2` | DOUBLE | Tile Coverage Area Km2 | km² | unavailable / inapplicable; see status/error |
| `meanTileAreaKm2` | DOUBLE | Mean Tile Area Km2 | km² | unavailable / inapplicable; see status/error |
| `medianTileAreaKm2` | DOUBLE | Median Tile Area Km2 | km² | unavailable / inapplicable; see status/error |
| `meanFeaturesPerTile` | DOUBLE | Mean Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `medianFeaturesPerTile` | DOUBLE | Median Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p90FeaturesPerTile` | DOUBLE | P90Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p95FeaturesPerTile` | DOUBLE | P95Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p99FeaturesPerTile` | DOUBLE | P99Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `meanStoredBytesPerTile` | DOUBLE | Mean Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `medianStoredBytesPerTile` | DOUBLE | Median Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `p90StoredBytesPerTile` | DOUBLE | P90Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `p95StoredBytesPerTile` | DOUBLE | P95Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `p99StoredBytesPerTile` | DOUBLE | P99Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `bytesPerFeature` | DOUBLE | Bytes Per Feature | bytes | unavailable / inapplicable; see status/error |
| `bytesPerVertex` | DOUBLE | Bytes Per Vertex; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `meanLayersPerTile` | DOUBLE | Mean Layers Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

## normalized_stats.sqlite

### analysis_errors

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stage` | VARCHAR | Stage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `errorType` | VARCHAR | Error Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `error` | VARCHAR | Recorded diagnostic error; NULL means no recorded error for this row | text | no recorded message/error |
| `traceback` | VARCHAR | Traceback; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### analysis_meta

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `schemaVersion` | INTEGER | Schema Version; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `analyzerVersion` | VARCHAR | Analyzer Version; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `generatedAt` | TEXT | Generated At | UTC timestamp | unavailable / inapplicable; see status/error |

### components

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentIndex` | INTEGER | Component Index; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `format` | VARCHAR | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fileBytes` | BIGINT | File Bytes | bytes | unavailable / inapplicable; see status/error |
| `tileEncoding` | VARCHAR | Tile Encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `crs` | VARCHAR | Crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `minZoom` | INTEGER | Min Zoom | zoom level | unavailable / inapplicable; see status/error |
| `maxZoom` | INTEGER | Max Zoom | zoom level | unavailable / inapplicable; see status/error |
| `structuralCount` | BIGINT | Structural Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `payloadBytes` | BIGINT | Payload Bytes | bytes | unavailable / inapplicable; see status/error |

### dataset_files

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT (PK) | Stable corpus identifier from analysis/datasets.json | identifier | not permitted |
| `map_name` | TEXT | Map name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stage` | TEXT | Stage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### field_values

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fieldName` | VARCHAR | Field Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | VARCHAR | Metadata or profiled source value; interpretation depends on key/table | text or source units | unavailable / inapplicable; see status/error |
| `valueType` | VARCHAR | Value Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `count` | BIGINT | Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fraction` | DOUBLE | Fraction; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### geometry_types

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceGeometryType` | VARCHAR | Source Geometry Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `analysisGeometryType` | VARCHAR | Analysis Geometry Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureCount` | BIGINT | Feature Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `linearized` | BOOLEAN | Linearized; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### layer_fields

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fieldName` | VARCHAR | Field Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `dataType` | VARCHAR | Data Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `populatedCount` | BIGINT | Populated Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `nullOrMissingCount` | BIGINT | Null Or Missing Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `distinctCount` | BIGINT | Distinct Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `distinctAtLeast` | BIGINT | Distinct At Least; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `cardinalityExceeded` | BOOLEAN | Cardinality Exceeded; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `fieldRole` | VARCHAR | Field Role; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### layer_mapping

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `source_layer` | TEXT | Source layer; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tile_layer` | TEXT | Tile layer; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `features` | INTEGER | Features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertices` | INTEGER | Vertices at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fields` | INTEGER | Fields at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### layers

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `declaredGeometry` | VARCHAR | Declared Geometry; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureInstances` | BIGINT | Feature Instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `featuresWithId` | BIGINT | Features With Id at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fieldCount` | BIGINT | Field Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `minZoom` | INTEGER | Min Zoom | zoom level | unavailable / inapplicable; see status/error |
| `maxZoom` | INTEGER | Max Zoom | zoom level | unavailable / inapplicable; see status/error |
| `semanticCategory` | VARCHAR | Semantic Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticSource` | VARCHAR | Semantic Source; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticConfidence` | DOUBLE | Semantic Confidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticEvidence` | VARCHAR | Semantic Evidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `countMeaning` | VARCHAR | Explicit interpretation of source or tile feature counts | text | unavailable / inapplicable; see status/error |
| `geometryLinearized` | BOOLEAN | Geometry Linearized; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### maps

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceFormat` | VARCHAR | Source Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mapKind` | VARCHAR | Map Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tileEncoding` | VARCHAR | Tile Encoding; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentCount` | BIGINT | Component Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fileBytes` | BIGINT | File Bytes | bytes | unavailable / inapplicable; see status/error |
| `crs` | VARCHAR | Crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `minZoom` | INTEGER | Min Zoom | zoom level | unavailable / inapplicable; see status/error |
| `maxZoom` | INTEGER | Max Zoom | zoom level | unavailable / inapplicable; see status/error |
| `title` | VARCHAR | Title; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `attribution` | VARCHAR | Attribution; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticCategory` | VARCHAR | Semantic Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticSource` | VARCHAR | Semantic Source; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticConfidence` | DOUBLE | Semantic Confidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `errorCount` | BIGINT | Error Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### meta

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `key` | TEXT (PK) | Key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `value` | TEXT | Metadata or profiled source value; interpretation depends on key/table | text or source units | not permitted |

### raster_bands

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentIndex` | INTEGER | Component Index; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `band` | INTEGER | Band; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `dataType` | VARCHAR | Data Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `width` | BIGINT | Width; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `height` | BIGINT | Height; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `validPixelCount` | BIGINT | Valid Pixel Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `noData` | DOUBLE | No Data; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `crs` | VARCHAR | Crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `resolutionX` | DOUBLE | Resolution X; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `resolutionY` | DOUBLE | Resolution Y; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `minimum` | DOUBLE | Minimum; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `maximum` | DOUBLE | Maximum; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mean` | DOUBLE | Mean; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `stddev` | DOUBLE | Stddev; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `uniqueValueCount` | BIGINT | Unique Value Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `valueMode` | VARCHAR | Value Mode; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `description` | VARCHAR | Description; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `unit` | VARCHAR | Unit; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `semanticCategory` | VARCHAR | Semantic Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### raster_values

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentIndex` | INTEGER | Component Index; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `band` | INTEGER | Band; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | VARCHAR | Metadata or profiled source value; interpretation depends on key/table | text or source units | unavailable / inapplicable; see status/error |
| `valueType` | VARCHAR | Value Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `pixelCount` | BIGINT | Pixel Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `fraction` | DOUBLE | Fraction; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### semantic_metadata

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `componentName` | VARCHAR | Component Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `key` | VARCHAR | Key; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | VARCHAR | Metadata or profiled source value; interpretation depends on key/table | text or source units | unavailable / inapplicable; see status/error |
| `sourceKind` | VARCHAR | Source Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### semantic_types

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceType` | VARCHAR | Source Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceField` | VARCHAR | Source Field; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceValue` | VARCHAR | Source Value; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `normalizedCategory` | VARCHAR | Normalized Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `normalizedType` | VARCHAR | Normalized Type; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sourceKind` | VARCHAR | Source Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `confidence` | DOUBLE | Confidence; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureCount` | BIGINT | Feature Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### study_area

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `declared_bounds` | TEXT | Declared bounds; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `actual_extent` | TEXT | Actual extent; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `area_km2` | REAL | Area km2 | km² | unavailable / inapplicable; see status/error |
| `bounds_ok` | INTEGER | Declared bounds contain the measured normalized extent | 0/1 | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### zoom_layers

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `layerName` | VARCHAR | Layer Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tileAppearances` | BIGINT | Tile Appearances; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `featureInstances` | BIGINT | Feature Instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `meanFeaturesPerTile` | DOUBLE | Mean Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `medianFeaturesPerTile` | DOUBLE | Median Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p95FeaturesPerTile` | DOUBLE | P95Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### zoom_stats

Definition and row grouping: [map_analysis_core.py](../analysis/map_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `mapName` | VARCHAR | Map Name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `tileCount` | BIGINT | Tile Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `featureInstances` | BIGINT | Feature Instances at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `vertexCount` | BIGINT | Vertex Count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `storedBytes` | BIGINT | Stored Bytes | bytes | unavailable / inapplicable; see status/error |
| `decodedBytes` | BIGINT | Decoded Bytes | bytes | unavailable / inapplicable; see status/error |
| `tileCoverageAreaKm2` | DOUBLE | Tile Coverage Area Km2 | km² | unavailable / inapplicable; see status/error |
| `meanTileAreaKm2` | DOUBLE | Mean Tile Area Km2 | km² | unavailable / inapplicable; see status/error |
| `medianTileAreaKm2` | DOUBLE | Median Tile Area Km2 | km² | unavailable / inapplicable; see status/error |
| `meanFeaturesPerTile` | DOUBLE | Mean Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `medianFeaturesPerTile` | DOUBLE | Median Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p90FeaturesPerTile` | DOUBLE | P90Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p95FeaturesPerTile` | DOUBLE | P95Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `p99FeaturesPerTile` | DOUBLE | P99Features Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `meanStoredBytesPerTile` | DOUBLE | Mean Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `medianStoredBytesPerTile` | DOUBLE | Median Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `p90StoredBytesPerTile` | DOUBLE | P90Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `p95StoredBytesPerTile` | DOUBLE | P95Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `p99StoredBytesPerTile` | DOUBLE | P99Stored Bytes Per Tile | bytes | unavailable / inapplicable; see status/error |
| `bytesPerFeature` | DOUBLE | Bytes Per Feature | bytes | unavailable / inapplicable; see status/error |
| `bytesPerVertex` | DOUBLE | Bytes Per Vertex; byte sum divided by vertex sum | bytes/vertex | unavailable / inapplicable; see status/error |
| `meanLayersPerTile` | DOUBLE | Mean Layers Per Tile at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

## tile_stats (Parquet)

Stored in `docs/data/tile_stats/` and distributed as `tile_stats_parquet.zip`.
SQL declarations below document logical types and keys; Parquet does not enforce
SQL constraints. The archive includes `schema.json` and `schema.sql`.

### analysis_errors

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `id` | INTEGER (PK) | Id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `map_id` | INTEGER | Map id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `archive_format` | TEXT | Archive format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `x` | INTEGER | Stored XYZ tile column at zoom z | tile index | unavailable / inapplicable; see status/error |
| `y` | INTEGER | Stored XYZ tile row at zoom z | tile index | unavailable / inapplicable; see status/error |
| `message` | TEXT | Message; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### archives

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `id` | INTEGER (PK) | Id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `map_id` | INTEGER | Map id; join key local to this database | identifier | not permitted |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `path` | TEXT | Path; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `file_bytes` | INTEGER | File bytes | bytes | not permitted |
| `pmtiles_version` | INTEGER | Pmtiles version at this table’s grain | count / as named | not permitted |
| `tile_type_code` | INTEGER | Tile type code; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `tile_compression` | TEXT | Tile compression; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `internal_compression` | TEXT | Internal compression; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `min_zoom` | INTEGER | Min zoom | zoom level | not permitted |
| `max_zoom` | INTEGER | Max zoom | zoom level | not permitted |
| `min_lon` | REAL | Min lon | degrees (WGS84) | not permitted |
| `min_lat` | REAL | Min lat | degrees (WGS84) | not permitted |
| `max_lon` | REAL | Max lon | degrees (WGS84) | not permitted |
| `max_lat` | REAL | Max lat | degrees (WGS84) | not permitted |
| `center_zoom` | INTEGER | Center zoom | zoom level | not permitted |
| `center_lon` | REAL | Center lon | degrees (WGS84) | not permitted |
| `center_lat` | REAL | Center lat | degrees (WGS84) | not permitted |
| `addressed_tiles_header` | INTEGER | Addressed tiles header at this table’s grain | count / as named | not permitted |
| `tile_entries_header` | INTEGER | Tile entries header; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `tile_contents_header` | INTEGER | Tile contents header; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `root_directory_bytes` | INTEGER | Root directory bytes | bytes | not permitted |
| `metadata_bytes` | INTEGER | Metadata bytes | bytes | not permitted |
| `leaf_directories_bytes` | INTEGER | Leaf directories bytes | bytes | not permitted |
| `tile_data_bytes` | INTEGER | Tile data bytes | bytes | not permitted |
| `clustered` | INTEGER | Clustered; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `metadata_json` | TEXT | Metadata json; serialized JSON metadata or sample | JSON | not permitted |

### gzip_check

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `n_tiles` | expression affinity | N tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `n_equal` | expression affinity | N equal; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sum_stored` | expression affinity | Sum stored; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sum_gzip6` | expression affinity | Sum gzip6; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `max_abs_diff` | expression affinity | Max abs diff; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### layers

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `layer_name` | TEXT (PK) | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `feature_instances` | INTEGER | Feature instances at this table’s grain | count / as named | not permitted |
| `min_zoom` | INTEGER | Min zoom | zoom level | unavailable / inapplicable; see status/error |
| `max_zoom` | INTEGER | Max zoom | zoom level | unavailable / inapplicable; see status/error |
| `min_extent` | INTEGER | Min extent; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `max_extent` | INTEGER | Max extent; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_versions` | TEXT | Mvt versions; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `semantic_key` | TEXT | Semantic key; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `point_instances` | INTEGER | Point instances at this table’s grain | count / as named | not permitted |
| `linestring_instances` | INTEGER | Linestring instances at this table’s grain | count / as named | not permitted |
| `polygon_instances` | INTEGER | Polygon instances at this table’s grain | count / as named | not permitted |
| `unknown_instances` | INTEGER | Unknown instances at this table’s grain | count / as named | not permitted |

### maps

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `id` | INTEGER (PK) | Id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `name` | TEXT | Name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `dataset_name` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | not permitted |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | not permitted |
| `density_factor` | INTEGER | Nominal represented tile-area factor: 1, 4 or 16 | factor | not permitted |
| `semantics_source` | TEXT | Semantics source; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `created_at_utc` | TEXT | Created at utc | UTC timestamp | not permitted |

### meta

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `key` | TEXT (PK) | Key; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value` | TEXT | Metadata or profiled source value; interpretation depends on key/table | text or source units | not permitted |

### mlt_layers

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `archive_id` | INTEGER (PK) | Archive id; join key local to this database | identifier | not permitted |
| `content_offset` | INTEGER (PK) | Stored payload offset used to identify deduplicated content in the archive | bytes | not permitted |
| `content_length` | INTEGER (PK) | Content length | bytes | not permitted |
| `layer_index` | INTEGER (PK) | Layer index; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `frame_tag` | INTEGER | Frame tag; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `extent` | INTEGER | Extent; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `column_count` | INTEGER | Column count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `feature_count` | INTEGER | Feature count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `raw_frame_bytes` | INTEGER | Raw frame bytes | bytes | not permitted |
| `isolated_gzip_frame_bytes` | INTEGER | Isolated gzip frame bytes | bytes | not permitted |
| `metadata_bytes` | INTEGER | Metadata bytes | bytes | unavailable / inapplicable; see status/error |
| `data_bytes` | INTEGER | Data bytes | bytes | unavailable / inapplicable; see status/error |
| `stream_count` | INTEGER | Stream count at this table’s grain | count / as named | not permitted |
| `stream_payload_bytes` | INTEGER | Stream payload bytes | bytes | not permitted |
| `stream_overhead_bytes` | INTEGER | Stream overhead bytes | bytes | not permitted |
| `parse_error` | TEXT | Parse error; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### mlt_streams

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `archive_id` | INTEGER (PK) | Archive id; join key local to this database | identifier | not permitted |
| `content_offset` | INTEGER (PK) | Stored payload offset used to identify deduplicated content in the archive | bytes | not permitted |
| `content_length` | INTEGER (PK) | Content length | bytes | not permitted |
| `layer_index` | INTEGER (PK) | Layer index; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `column_index` | INTEGER (PK) | Column index; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `column_name` | TEXT (PK) | Column name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `column_type` | TEXT | Column type; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `stream_index` | INTEGER (PK) | Stream index; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `stream_type_code` | INTEGER | Stream type code; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `stream_category` | TEXT | Stream category; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `stream_subtype` | TEXT | Stream subtype; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `stream_role` | TEXT | Stream role; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `encoding_code` | INTEGER | Encoding code; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `logical_encoding` | TEXT | Logical encoding; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `physical_encoding` | TEXT | Physical encoding; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `num_values` | INTEGER | Num values at this table’s grain | count / as named | not permitted |
| `payload_bytes` | INTEGER | Payload bytes | bytes | not permitted |
| `header_bytes` | INTEGER | Header bytes | bytes | not permitted |
| `total_bytes` | INTEGER | Total bytes | bytes | not permitted |
| `runs` | INTEGER | Runs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `num_rle_values` | INTEGER | Num rle values at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `morton_bits` | INTEGER | Morton bits; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `morton_shift` | INTEGER | Morton shift; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### pair_validation

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `mvt_tile_count` | INTEGER | Mvt tile count at this table’s grain | count / as named | not permitted |
| `mlt_tile_count` | INTEGER | Mlt tile count at this table’s grain | count / as named | not permitted |
| `missing_in_mlt` | INTEGER | Missing in mlt; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `missing_in_mvt` | INTEGER | Missing in mvt; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `same_tile_coordinates` | INTEGER | Same tile coordinates; see the table implementation for its exact definition | dimensionless / text | not permitted |

### parser_checks

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INT | Map id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `archive_id` | INT | Archive id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `layer_frames` | expression affinity | Layer frames at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `failed_frames` | expression affinity | Failed frames at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `frame_bytes` | expression affinity | Frame bytes | bytes | unavailable / inapplicable; see status/error |
| `stream_bytes` | expression affinity | Stream bytes | bytes | unavailable / inapplicable; see status/error |

### properties

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `layer_name` | TEXT (PK) | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `property_key` | TEXT (PK) | Property key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `feature_occurrences` | INTEGER | Feature occurrences at this table’s grain | count / as named | not permitted |
| `value_types` | TEXT | Value types; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `distinct_values_capped` | INTEGER | Distinct values capped at this table’s grain | count / as named | not permitted |
| `high_cardinality` | INTEGER | High cardinality; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `sample_values_json` | TEXT | Sample values json; serialized JSON metadata or sample | JSON | not permitted |
| `min_zoom` | INTEGER | Min zoom | zoom level | unavailable / inapplicable; see status/error |
| `max_zoom` | INTEGER | Max zoom | zoom level | unavailable / inapplicable; see status/error |

### property_values

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `layer_name` | TEXT (PK) | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `property_key` | TEXT (PK) | Property key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `property_value` | TEXT (PK) | Property value; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `geometry_type` | TEXT (PK) | Geometry type; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `zoom` | INTEGER (PK) | Zoom | zoom level | not permitted |
| `feature_instances` | INTEGER | Feature instances at this table’s grain | count / as named | not permitted |

### semantic_types

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `layer_name` | TEXT (PK) | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `semantic_key` | TEXT (PK) | Semantic key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `semantic_value` | TEXT (PK) | Semantic value; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `geometry_type` | TEXT (PK) | Geometry type; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `zoom` | INTEGER (PK) | Zoom | zoom level | not permitted |
| `feature_instances` | INTEGER | Feature instances at this table’s grain | count / as named | not permitted |

### tile_content_stats

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `z` | INTEGER (PK) | Stored Web Mercator XYZ zoom level | zoom level | not permitted |
| `x` | INTEGER (PK) | Stored XYZ tile column at zoom z | tile index | not permitted |
| `y` | INTEGER (PK) | Stored XYZ tile row at zoom z | tile index | not permitted |
| `feature_instances` | INTEGER | Feature instances at this table’s grain | count / as named | not permitted |
| `vertex_count` | INTEGER | Vertex count at this table’s grain | count / as named | not permitted |
| `geometry_command_ints` | INTEGER | Geometry command ints; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `geometry_command_count` | INTEGER | Geometry command count at this table’s grain | count / as named | not permitted |
| `tag_pairs` | INTEGER | Tag pairs; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `layer_count` | INTEGER | Layer count at this table’s grain | count / as named | not permitted |
| `property_key_count` | INTEGER | Property key count at this table’s grain | count / as named | not permitted |
| `property_value_count` | INTEGER | Property value count at this table’s grain | count / as named | not permitted |

### tile_layer_stats

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `z` | INTEGER (PK) | Stored Web Mercator XYZ zoom level | zoom level | not permitted |
| `x` | INTEGER (PK) | Stored XYZ tile column at zoom z | tile index | not permitted |
| `y` | INTEGER (PK) | Stored XYZ tile row at zoom z | tile index | not permitted |
| `layer_name` | TEXT (PK) | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `geometry_type` | TEXT (PK) | Geometry type; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `feature_instances` | INTEGER | Feature instances at this table’s grain | count / as named | not permitted |
| `vertex_count` | INTEGER | Vertex count at this table’s grain | count / as named | not permitted |
| `geometry_command_ints` | INTEGER | Geometry command ints; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `geometry_command_count` | INTEGER | Geometry command count at this table’s grain | count / as named | not permitted |
| `tag_pairs` | INTEGER | Tag pairs; see the table implementation for its exact definition | dimensionless / text | not permitted |

### tile_layers

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `map_id` | INTEGER (PK) | Map id; join key local to this database | identifier | not permitted |
| `z` | INTEGER (PK) | Stored Web Mercator XYZ zoom level | zoom level | not permitted |
| `x` | INTEGER (PK) | Stored XYZ tile column at zoom z | tile index | not permitted |
| `y` | INTEGER (PK) | Stored XYZ tile row at zoom z | tile index | not permitted |
| `layer_name` | TEXT (PK) | Layer name; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `extent` | INTEGER | Extent; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `mvt_version` | INTEGER | Mvt version; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `feature_instances` | INTEGER | Feature instances at this table’s grain | count / as named | not permitted |
| `vertex_count` | INTEGER | Vertex count at this table’s grain | count / as named | not permitted |
| `geometry_command_ints` | INTEGER | Geometry command ints; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `geometry_command_count` | INTEGER | Geometry command count at this table’s grain | count / as named | not permitted |
| `tag_pairs` | INTEGER | Tag pairs; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `mvt_raw_layer_bytes` | INTEGER | Mvt raw layer bytes | bytes | not permitted |
| `mvt_isolated_gzip_layer_bytes` | INTEGER | Mvt isolated gzip layer bytes | bytes | not permitted |
| `mvt_key_count` | INTEGER | Mvt key count at this table’s grain | count / as named | not permitted |
| `mvt_value_count` | INTEGER | Mvt value count at this table’s grain | count / as named | not permitted |
| `mvt_key_utf8_bytes` | INTEGER | Mvt key utf8 bytes | bytes | not permitted |
| `mvt_value_proto_bytes` | INTEGER | Mvt value proto bytes | bytes | not permitted |

### tiles

Definition and row grouping: [output_analysis_core.py](../analysis/output_analysis_core.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `archive_id` | INTEGER (PK) | Archive id; join key local to this database | identifier | not permitted |
| `z` | INTEGER (PK) | Stored Web Mercator XYZ zoom level | zoom level | not permitted |
| `x` | INTEGER (PK) | Stored XYZ tile column at zoom z | tile index | not permitted |
| `y` | INTEGER (PK) | Stored XYZ tile row at zoom z | tile index | not permitted |
| `stored_bytes` | INTEGER | Original stored PMTiles payload length | bytes | not permitted |
| `raw_payload_bytes` | INTEGER | Decompressed tile payload length | bytes | unavailable / inapplicable; see status/error |
| `gzip_payload_bytes` | INTEGER | Uniform gzip-6 payload length, mtime=0 | bytes | unavailable / inapplicable; see status/error |
| `content_offset` | INTEGER | Stored payload offset used to identify deduplicated content in the archive | bytes | not permitted |
| `logical_zoom` | INTEGER | Stored zoom plus detail offset 0/1/2 | zoom level | unavailable / inapplicable; see status/error |

## audit_stats.sqlite

### bounds

Definition and row grouping: [audit.py](../analysis/audit.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `id` | INTEGER (PK) | Id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `stage` | TEXT | Stage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `kind` | TEXT | Kind; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `component` | TEXT | Component; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `zoom` | INTEGER | Zoom | zoom level | unavailable / inapplicable; see status/error |
| `min_lon` | REAL | Min lon | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `min_lat` | REAL | Min lat | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `max_lon` | REAL | Max lon | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `max_lat` | REAL | Max lat | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `native_crs` | TEXT | Native crs; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `native_bounds_json` | TEXT | Native bounds json; serialized JSON metadata or sample | JSON | unavailable / inapplicable; see status/error |
| `path` | TEXT | Path; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `sha256` | TEXT | Sha256; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `method` | TEXT | Method; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `details_json` | TEXT | Details json; serialized JSON metadata or sample | JSON | unavailable / inapplicable; see status/error |

### bounds_checks

Definition and row grouping: [audit.py](../analysis/audit.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `zoom` | INTEGER | Zoom | zoom level | unavailable / inapplicable; see status/error |
| `check_name` | TEXT | Check name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `tolerance_degrees` | REAL | Tolerance degrees | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `west_excess` | REAL | West excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `south_excess` | REAL | South excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `east_excess` | REAL | East excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `north_excess` | REAL | North excess | degrees (WGS84) | unavailable / inapplicable; see status/error |
| `message` | TEXT | Message; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### meta

Definition and row grouping: [audit.py](../analysis/audit.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `key` | TEXT (PK) | Key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `value` | TEXT | Metadata or profiled source value; interpretation depends on key/table | text or source units | not permitted |

### validation

Definition and row grouping: [audit.py](../analysis/audit.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT (PK) | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT (PK) | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `mode` | TEXT | Mode; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_path` | TEXT | Mvt path; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mlt_path` | TEXT | Mlt path; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_sha256` | TEXT | Mvt sha256; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mlt_sha256` | TEXT | Mlt sha256; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `mvt_tiles` | INTEGER | Mvt tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_tiles` | INTEGER | Mlt tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `checked_tiles` | INTEGER | Checked tiles at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mismatches` | INTEGER | Mismatches at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `errors` | INTEGER | Errors at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `missing_mvt` | INTEGER | Missing mvt; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `missing_mlt` | INTEGER | Missing mlt; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `passed` | INTEGER | Strict comparison pass flag; diagnostic, not an acceptance gate | 0/1 | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `elapsed_seconds` | REAL | Elapsed seconds | seconds | unavailable / inapplicable; see status/error |
| `validated_at_utc` | TEXT | Validated at utc | UTC timestamp | unavailable / inapplicable; see status/error |

### validation_issues

Definition and row grouping: [audit.py](../analysis/audit.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `x` | INTEGER | Stored XYZ tile column at zoom z | tile index | unavailable / inapplicable; see status/error |
| `y` | INTEGER | Stored XYZ tile row at zoom z | tile index | unavailable / inapplicable; see status/error |
| `category` | TEXT | Category; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `details_json` | TEXT | Details json; serialized JSON metadata or sample | JSON | unavailable / inapplicable; see status/error |

## type_stats.sqlite

### attribute_payload_pairs

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INTEGER (PK) | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `mvt_offset` | INTEGER | Mvt offset | bytes | unavailable / inapplicable; see status/error |
| `mvt_length` | INTEGER | Mvt length | bytes | unavailable / inapplicable; see status/error |
| `mlt_offset` | INTEGER | Mlt offset | bytes | unavailable / inapplicable; see status/error |
| `mlt_length` | INTEGER | Mlt length | bytes | unavailable / inapplicable; see status/error |
| `address_count` | INTEGER | Number of tile addresses reusing this payload pair | count | unavailable / inapplicable; see status/error |
| `status` | TEXT | Status; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |

### attribute_tile_addresses

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INTEGER | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `z` | INTEGER | Stored Web Mercator XYZ zoom level | zoom level | unavailable / inapplicable; see status/error |
| `x` | INTEGER | Stored XYZ tile column at zoom z | tile index | unavailable / inapplicable; see status/error |
| `y` | INTEGER | Stored XYZ tile row at zoom z | tile index | unavailable / inapplicable; see status/error |

### attribute_transitions

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `property_name` | TEXT | Property name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `before_type` | TEXT | MVT protobuf Value type before transcoding | type label | unavailable / inapplicable; see status/error |
| `after_type` | TEXT | MLT declared column type after transcoding | type label | unavailable / inapplicable; see status/error |
| `after_nullable` | INT | MLT declared column permits NULL; does not measure actual NULL count | 0/1 | unavailable / inapplicable; see status/error |
| `after_storage` | TEXT | After storage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `transition` | TEXT | Transition; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `column_type_tile_occurrences` | expression affinity | Column type tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_occurrences` | expression affinity | Present property values, already weighted by tile-address multiplicity | count | unavailable / inapplicable; see status/error |
| `mixed_source_value_occurrences` | expression affinity | Mixed source value occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### attribute_type_errors

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INTEGER | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `format` | TEXT | Format; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `message` | TEXT | Message; see the table implementation for its exact definition | dimensionless / text | no recorded message/error |

### attribute_type_profiles

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `pair_id` | INTEGER | Pair id; join key local to this database | identifier | unavailable / inapplicable; see status/error |
| `layer_name` | TEXT | Layer name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `property_name` | TEXT | Property name; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `before_type` | TEXT | MVT protobuf Value type before transcoding | type label | unavailable / inapplicable; see status/error |
| `after_type` | TEXT | MLT declared column type after transcoding | type label | unavailable / inapplicable; see status/error |
| `after_nullable` | INTEGER | MLT declared column permits NULL; does not measure actual NULL count | 0/1 | unavailable / inapplicable; see status/error |
| `after_storage` | TEXT | After storage; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `value_count` | INTEGER | Value count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mvt_features` | INTEGER | Mvt features at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `absent_count` | INTEGER | Missing property count per payload; repeated across original-type rows, not additive | count | unavailable / inapplicable; see status/error |
| `source_type_count` | INTEGER | Source type count at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `transition` | TEXT | Transition; see the table implementation for its exact definition | dimensionless / text | unavailable / inapplicable; see status/error |
| `before_examples_json` | TEXT | Sample original attribute values; upstream source terms apply | JSON | unavailable / inapplicable; see status/error |

### attribute_type_summary

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `dataset_id` | TEXT | Stable corpus identifier from analysis/datasets.json | identifier | unavailable / inapplicable; see status/error |
| `variant` | TEXT | Pyramid variant: standard, dense4 or dense16 | label | unavailable / inapplicable; see status/error |
| `property_tile_occurrences` | expression affinity | Property tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mixed_property_tile_occurrences` | expression affinity | Mixed property tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `value_occurrences` | expression affinity | Present property values, already weighted by tile-address multiplicity | count | unavailable / inapplicable; see status/error |
| `to_string_value_occurrences` | expression affinity | To string value occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `missing_column_tile_occurrences` | expression affinity | Missing column tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |
| `mlt_only_column_tile_occurrences` | expression affinity | Mlt only column tile occurrences at this table’s grain | count / as named | unavailable / inapplicable; see status/error |

### meta

Definition and row grouping: [attribute_types.py](../analysis/attribute_types.py).

| Column | SQLite declaration | Meaning | Unit | NULL |
|---|---|---|---|---|
| `key` | TEXT (PK) | Key; see the table implementation for its exact definition | dimensionless / text | not permitted |
| `value` | TEXT | Metadata or profiled source value; interpretation depends on key/table | text or source units | not permitted |

