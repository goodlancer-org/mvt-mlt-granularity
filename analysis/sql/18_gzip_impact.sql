-- Quantify how the old stored-gzip convention differs from uniform gzip-6.
-- Both ratios use the same paired tile addresses and full precision.
CREATE TABLE gzip_impact AS
WITH savings AS (
 SELECT dataset_name AS dataset_id,variant,
   100.0*(1.0-SUM(mlt_stored_bytes)*1.0/NULLIF(SUM(mvt_stored_bytes),0)) AS stored_saving_pct,
   100.0*(1.0-SUM(mlt_gzip_bytes)*1.0/NULLIF(SUM(mvt_gzip_bytes),0)) AS gzip6_saving_pct
 FROM v_tile_comparison GROUP BY dataset_name,variant
)
SELECT *,gzip6_saving_pct-stored_saving_pct AS delta_pp,'address_weighted' AS weighting
FROM savings;
