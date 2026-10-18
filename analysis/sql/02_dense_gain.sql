-- Ported from docs/output_analysis.sql; full precision until report.
CREATE TABLE dense_gain AS
SELECT
        dataset_name,

        MAX(CASE
            WHEN variant = 'standard'
            THEN raw_saving_pct
        END) AS standard_raw_pct,

        MAX(CASE
            WHEN variant = 'dense4'
            THEN raw_saving_pct
        END) AS dense4_raw_pct,

        MAX(CASE
            WHEN variant = 'dense16'
            THEN raw_saving_pct
        END) AS dense16_raw_pct,

        MAX(CASE
            WHEN variant = 'standard'
            THEN after_gzip_saving_pct
        END) AS standard_after_gzip_pct,

        MAX(CASE
            WHEN variant = 'dense4'
            THEN after_gzip_saving_pct
        END) AS dense4_after_gzip_pct,

        MAX(CASE
            WHEN variant = 'dense16'
            THEN after_gzip_saving_pct
        END) AS dense16_after_gzip_pct

    FROM variant_compression
    GROUP BY dataset_name;
