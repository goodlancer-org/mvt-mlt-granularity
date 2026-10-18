-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE layer_compression AS
SELECT
        dataset_name,
        variant,
        density_factor,
        layer_name,

        COUNT(*) AS tile_count,
        SUM(feature_instances) AS feature_count,
        SUM(vertex_count) AS vertex_count,

        (
            SUM(mvt_raw_layer_bytes) / 1048576.0) AS mvt_raw_mib,

        (
            SUM(mlt_raw_layer_bytes) / 1048576.0) AS mlt_raw_mib,

        (
            100.0 * (
                1.0 -
                SUM(mlt_raw_layer_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_layer_bytes), 0)
            )) AS mlt_raw_saving_pct,

        SUM(mvt_key_count) AS mvt_key_count,
        SUM(mvt_value_count) AS mvt_value_count,

        SUM(mlt_stream_count) AS mlt_stream_count,

        (
            SUM(mlt_stream_payload_bytes) / 1048576.0) AS stream_payload_mib,

        (
            SUM(mlt_stream_overhead_bytes) / 1048576.0) AS stream_overhead_mib,

        (
            100.0 *
            SUM(mlt_stream_overhead_bytes) /
            NULLIF(
                SUM(mlt_stream_payload_bytes) +
                SUM(mlt_stream_overhead_bytes),
                0
            )) AS stream_overhead_pct,

        SUM(mlt_parse_errors) AS parse_error_count

    FROM v_tile_layer_comparison
    WHERE mlt_raw_layer_bytes IS NOT NULL

    GROUP BY
        dataset_name,
        variant,
        density_factor,
        layer_name;
