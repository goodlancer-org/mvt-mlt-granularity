-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE layer_count_summary AS
SELECT
        layer_count,
        COUNT(*) AS tile_count,

        (AVG(feature_instances)) AS avg_features,
        (AVG(vertex_count)) AS avg_vertices,

        (
            100.0 * (
                1.0 -
                SUM(mlt_raw_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            )) AS mlt_raw_saving_pct,

        (
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_gzip_bytes), 0)
            )) AS mlt_after_gzip_saving_pct

    FROM v_tile_comparison
    GROUP BY layer_count;
