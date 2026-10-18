CREATE TABLE granularity_gain AS
SELECT v.dataset_name AS dataset_id,v.variant,
       v.raw_saving_pct-s.raw_saving_pct AS g_raw,
       v.after_gzip_saving_pct-s.after_gzip_saving_pct AS g_gz,
       'address_weighted' AS weighting
FROM variant_compression v JOIN variant_compression s USING(dataset_name)
WHERE s.variant='standard' AND v.variant!='standard';

CREATE TABLE zoom_comparison AS
SELECT v.dataset_name AS dataset_id,v.logical_z,
       v.mlt_raw_saving_pct-s.mlt_raw_saving_pct AS delta_raw,
       v.mlt_after_gzip_saving_pct-s.mlt_after_gzip_saving_pct AS delta_gz,
       CASE WHEN ABS(v.mlt_raw_saving_pct-s.mlt_raw_saving_pct)<0.05 THEN 'equal'
            WHEN v.mlt_raw_saving_pct>s.mlt_raw_saving_pct THEN 'higher' ELSE 'lower' END AS raw_class,
       CASE WHEN ABS(v.mlt_after_gzip_saving_pct-s.mlt_after_gzip_saving_pct)<0.05 THEN 'equal'
            WHEN v.mlt_after_gzip_saving_pct>s.mlt_after_gzip_saving_pct THEN 'higher' ELSE 'lower' END AS gz_class
FROM logical_zoom_summary v JOIN logical_zoom_summary s USING(dataset_name,logical_z)
WHERE v.variant='dense16' AND s.variant='standard';

CREATE TABLE bytes_per_vertex AS
SELECT dataset_name AS dataset_id,variant,SUM(vertex_count) AS vertices,
       SUM(mvt_raw_bytes)*1.0/NULLIF(SUM(vertex_count),0) AS mvt_raw,
       SUM(mlt_raw_bytes)*1.0/NULLIF(SUM(vertex_count),0) AS mlt_raw,
       SUM(mvt_gzip_bytes)*1.0/NULLIF(SUM(vertex_count),0) AS mvt_gzip6,
       SUM(mlt_gzip_bytes)*1.0/NULLIF(SUM(vertex_count),0) AS mlt_gzip6
FROM v_tile_comparison GROUP BY dataset_name,variant;

CREATE TABLE archive_totals AS
WITH totals AS (
 SELECT m.dataset_name AS dataset_id,m.variant,a.format,SUM(t.gzip_payload_bytes) AS gzip6_bytes
 FROM tile.tiles t JOIN tile.archives a ON a.id=t.archive_id JOIN tile.maps m ON m.id=a.map_id
 GROUP BY m.dataset_name,m.variant,a.format
)
SELECT t.*,100.0*(t.gzip6_bytes*1.0/NULLIF(s.gzip6_bytes,0)-1) AS change_vs_standard_pct,
       'address_weighted' AS weighting
FROM totals t JOIN totals s USING(dataset_id,format) WHERE s.variant='standard';

CREATE TABLE stream_summary AS
SELECT t.*,t.value_count*1.0/NULLIF(t.stream_count,0) AS values_per_stream,
       t.header_bytes*1.0/NULLIF(t.stream_bytes,0) AS stream_header_share,
       t.payload_bytes*1.0/NULLIF(t.value_count,0) AS payload_bytes_per_value,
       (c.frame_bytes-t.payload_bytes)*1.0/NULLIF(c.frame_bytes,0) AS r_struct,
       'payload_weighted' AS weighting
FROM stream_totals t JOIN layer_parse_coverage c USING(dataset_name,variant);
