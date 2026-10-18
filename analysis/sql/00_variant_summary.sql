-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE variant_summary AS
SELECT
        dataset_name,
        variant,
        density_factor,

        COUNT(*) AS tile_count,
        SUM(feature_instances) AS feature_count,
        SUM(vertex_count) AS vertex_count,

        (AVG(feature_instances)) AS avg_features_per_tile,
        (AVG(vertex_count)) AS avg_vertices_per_tile,
        (AVG(layer_count)) AS avg_layers_per_tile,

        (SUM(mvt_raw_bytes) / 1048576.0) AS mvt_raw_mib,
        (SUM(mvt_gzip_bytes) / 1048576.0) AS mvt_gzip_mib,
        (SUM(mlt_raw_bytes) / 1048576.0) AS mlt_raw_mib,
        (SUM(mlt_gzip_bytes) / 1048576.0) AS mlt_gzip_mib,

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
            )) AS mlt_after_gzip_saving_pct,

        (
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            )) AS total_mlt_gzip_saving_pct,

        (
            SUM(mvt_raw_bytes) * 1.0 /
            NULLIF(SUM(feature_instances), 0)) AS mvt_raw_bytes_per_feature,

        (
            SUM(mlt_raw_bytes) * 1.0 /
            NULLIF(SUM(feature_instances), 0)) AS mlt_raw_bytes_per_feature,

        (
            SUM(mvt_raw_bytes) * 1.0 /
            NULLIF(SUM(vertex_count), 0)) AS mvt_raw_bytes_per_vertex,

        (
            SUM(mlt_raw_bytes) * 1.0 /
            NULLIF(SUM(vertex_count), 0)) AS mlt_raw_bytes_per_vertex,

        
        (SUM(mvt_gzip_bytes) * 1.0 / NULLIF(SUM(vertex_count), 0)) AS mvt_gzip_bytes_per_vertex,
        (SUM(mlt_gzip_bytes) * 1.0 / NULLIF(SUM(vertex_count), 0)) AS mlt_gzip_bytes_per_vertex

    FROM v_tile_comparison
    GROUP BY
        dataset_name,
        variant,
        density_factor;
