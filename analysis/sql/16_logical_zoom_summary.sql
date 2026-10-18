-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE logical_zoom_summary AS
SELECT
        dataset_name,
        variant,
        density_factor,
        z + CASE density_factor WHEN 1 THEN 0 WHEN 4 THEN 1 WHEN 16 THEN 2 END AS logical_z,
        COUNT(*) AS tile_count,
        (AVG(vertex_count)) AS avg_vertices_per_tile,
        SUM(mvt_raw_bytes) AS mvt_raw_bytes,
        SUM(mvt_gzip_bytes) AS mvt_gzip_bytes,
        SUM(mlt_raw_bytes) AS mlt_raw_bytes,
        SUM(mlt_gzip_bytes) AS mlt_gzip_bytes,
        (100.0 * (1.0 - SUM(mlt_raw_bytes) * 1.0 / NULLIF(SUM(mvt_raw_bytes), 0))) AS mlt_raw_saving_pct,
        (100.0 * (1.0 - SUM(mlt_gzip_bytes) * 1.0 / NULLIF(SUM(mvt_gzip_bytes), 0))) AS mlt_after_gzip_saving_pct
    FROM v_tile_comparison
    GROUP BY dataset_name, variant, density_factor, logical_z;
