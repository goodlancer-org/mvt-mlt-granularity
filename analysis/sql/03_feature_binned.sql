-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE feature_binned AS
SELECT
        CASE
            WHEN feature_instances = 0 THEN '000000'
            WHEN feature_instances < 10 THEN '000001-000009'
            WHEN feature_instances < 50 THEN '000010-000049'
            WHEN feature_instances < 100 THEN '000050-000099'
            WHEN feature_instances < 500 THEN '000100-000499'
            WHEN feature_instances < 1000 THEN '000500-000999'
            WHEN feature_instances < 5000 THEN '001000-004999'
            WHEN feature_instances < 10000 THEN '005000-009999'
            ELSE '010000+'
        END AS feature_bin,

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
