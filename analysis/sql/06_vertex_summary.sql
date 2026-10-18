-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE vertex_summary AS
SELECT
        vertex_bin,

        COUNT(*) AS tile_count,

        (AVG(vertex_count)) AS avg_vertices,
        (AVG(feature_instances)) AS avg_features,
        (AVG(layer_count)) AS avg_layers,
        (AVG(mvt_raw_bytes) / 1024.0) AS avg_mvt_raw_kib,

        (
            100.0 * (
                1.0 -
                SUM(mvt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            )) AS mvt_gzip_saving_pct,

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

    FROM vertex_binned
    GROUP BY vertex_bin;
