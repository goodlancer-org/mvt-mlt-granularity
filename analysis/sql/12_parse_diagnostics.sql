-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE parse_diagnostics AS
SELECT
        m.dataset_name,
        m.variant,
        ml.layer_name,
        ml.frame_tag,
        ml.parse_error,
        COUNT(*) AS occurrence_count

    FROM mlt_layers ml
    JOIN archives a
        ON a.id = ml.archive_id
    JOIN maps m
        ON m.id = a.map_id

    WHERE ml.parse_error IS NOT NULL

    GROUP BY
        m.dataset_name,
        m.variant,
        ml.layer_name,
        ml.frame_tag,
        ml.parse_error;
