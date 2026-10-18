-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE mlt_stream_layer_summary AS
SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,

        s.stream_role,
        s.logical_encoding,
        s.physical_encoding,

        COUNT(*) AS stream_count,
        SUM(s.num_values) AS value_count,

        (
            SUM(s.total_bytes) / 1024.0) AS total_kib,

        (
            SUM(s.total_bytes) * 1.0 /
            NULLIF(SUM(s.num_values), 0)) AS bytes_per_value

    FROM mlt_streams s
    JOIN archives a
        ON a.id = s.archive_id
    JOIN maps m
        ON m.id = a.map_id

    GROUP BY
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,
        s.stream_role,
        s.logical_encoding,
        s.physical_encoding;
