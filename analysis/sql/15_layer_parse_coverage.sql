-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE layer_parse_coverage AS
SELECT
        m.dataset_name,
        m.variant,
        COUNT(*) AS layer_frames,
        SUM(CASE WHEN ml.parse_error IS NOT NULL THEN 1 ELSE 0 END) AS failed_frames,
        SUM(ml.raw_frame_bytes) AS frame_bytes,
        SUM(CASE WHEN ml.parse_error IS NOT NULL THEN ml.raw_frame_bytes ELSE 0 END) AS failed_frame_bytes
    FROM mlt_layers ml
    JOIN archives a ON a.id = ml.archive_id
    JOIN maps m ON m.id = a.map_id
    GROUP BY m.dataset_name, m.variant;
