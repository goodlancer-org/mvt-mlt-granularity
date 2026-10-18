-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE mlt_stream_summary AS
SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,

        s.stream_role,
        s.logical_encoding,
        s.physical_encoding,

        COUNT(*) AS stream_count,
        SUM(s.num_values) AS value_count,

        (
            SUM(s.payload_bytes) / 1048576.0) AS payload_mib,

        (
            SUM(s.header_bytes) / 1048576.0) AS header_mib,

        (
            SUM(s.total_bytes) / 1048576.0) AS total_mib,

        (
            AVG(s.num_values)) AS avg_values_per_stream,

        (
            SUM(s.total_bytes) * 1.0 /
            NULLIF(SUM(s.num_values), 0)) AS bytes_per_value,

        (
            100.0 *
            SUM(s.header_bytes) /
            NULLIF(SUM(s.total_bytes), 0)) AS header_overhead_pct

    FROM mlt_streams s
    JOIN archives a
        ON a.id = s.archive_id
    JOIN maps m
        ON m.id = a.map_id

    GROUP BY
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.stream_role,
        s.logical_encoding,
        s.physical_encoding;
