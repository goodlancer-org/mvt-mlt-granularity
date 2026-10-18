-- [ADDED] Per-tile table for Zenodo and for tile-level statistics (one row per tile address).
-- Export, e.g.:  sqlite3 -header -csv analysis.sqlite < per_tile_export.sql > per_tile.csv
SELECT
    dataset_name, variant, density_factor, z, x, y,
    z + CASE density_factor WHEN 1 THEN 0 WHEN 4 THEN 1 WHEN 16 THEN 2 END AS logical_z,
    feature_instances, vertex_count, layer_count, tag_pairs,
    mvt_raw_bytes, mvt_gzip_bytes, mlt_raw_bytes, mlt_gzip_bytes
FROM v_tile_comparison
ORDER BY dataset_name, density_factor, z, x, y;