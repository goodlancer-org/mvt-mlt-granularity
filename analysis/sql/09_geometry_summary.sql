-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE geometry_summary AS
SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,
        s.geometry_type,

        SUM(s.feature_instances) AS feature_count,
        SUM(s.vertex_count) AS vertex_count,

        (
            SUM(s.vertex_count) * 1.0 /
            NULLIF(SUM(s.feature_instances), 0)) AS vertices_per_feature

    FROM tile_layer_stats s
    JOIN maps m
        ON m.id = s.map_id

    GROUP BY
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,
        s.geometry_type;
