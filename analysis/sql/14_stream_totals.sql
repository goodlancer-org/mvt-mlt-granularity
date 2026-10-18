-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE stream_totals AS
SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,
        COUNT(*) AS stream_count,
        SUM(s.num_values) AS value_count,
        SUM(s.header_bytes) AS header_bytes,
        SUM(s.payload_bytes) AS payload_bytes,
        SUM(s.total_bytes) AS stream_bytes
    FROM mlt_streams s
    JOIN archives a ON a.id = s.archive_id
    JOIN maps m ON m.id = a.map_id
    GROUP BY m.dataset_name, m.variant, m.density_factor;
