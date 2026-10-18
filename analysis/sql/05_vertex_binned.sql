-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE vertex_binned AS
SELECT
        CASE
            WHEN vertex_count = 0 THEN '000000'
            WHEN vertex_count < 100 THEN '000001-000099'
            WHEN vertex_count < 500 THEN '000100-000499'
            WHEN vertex_count < 1000 THEN '000500-000999'
            WHEN vertex_count < 5000 THEN '001000-004999'
            WHEN vertex_count < 10000 THEN '005000-009999'
            WHEN vertex_count < 50000 THEN '010000-049999'
            WHEN vertex_count < 100000 THEN '050000-099999'
            ELSE '100000+'
        END AS vertex_bin,

        dataset_name,          
        variant,               
        feature_instances,
        vertex_count,
        layer_count,
        mvt_raw_bytes,
        mvt_gzip_bytes,
        mlt_raw_bytes,
        mlt_gzip_bytes

    FROM v_tile_comparison;
