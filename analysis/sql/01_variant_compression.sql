-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE variant_compression AS
SELECT
        dataset_name,
        variant,

        100.0 * (
            1.0 -
            SUM(mlt_raw_bytes) * 1.0 /
            NULLIF(SUM(mvt_raw_bytes), 0)
        ) AS raw_saving_pct,

        100.0 * (
            1.0 -
            SUM(mlt_gzip_bytes) * 1.0 /
            NULLIF(SUM(mvt_gzip_bytes), 0)
        ) AS after_gzip_saving_pct

    FROM v_tile_comparison
    GROUP BY dataset_name, variant;
