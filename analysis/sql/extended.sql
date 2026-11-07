-- All byte sums below are address-weighted unless explicitly named stored_unique.
CREATE VIEW tile_content AS
SELECT dataset,variant,payload_key,SUM(feature_instances) features,SUM(vertices) vertices,
 SUM(fragments) fragments,SUM(repeated_vertices) repeated_vertices
FROM content GROUP BY ALL;
CREATE VIEW measured AS SELECT a.*,p.format,p.raw_bytes,p.gzip_bytes,p.content_sha256,
 COALESCE(c.features,0) features,COALESCE(c.vertices,0) vertices,COALESCE(c.fragments,0) fragments,
 COALESCE(c.repeated_vertices,0) repeated_vertices
FROM addresses a JOIN payloads p USING(dataset,variant,payload_key)
LEFT JOIN tile_content c USING(dataset,variant,payload_key);
CREATE TABLE archive_summary AS
WITH sizes AS (SELECT dataset,variant,factor,format,COUNT(*) tiles,SUM(raw_bytes) raw_bytes,
 SUM(gzip_bytes) gzip_bytes,SUM(features) features,SUM(vertices) vertices,SUM(fragments) fragments
 FROM measured GROUP BY ALL),
unique_sizes AS (SELECT dataset,variant,format,SUM(raw_bytes) stored_unique_raw_bytes,
 SUM(gzip_bytes) stored_unique_gzip_bytes,COUNT(*) stored_unique_payloads FROM
 (SELECT DISTINCT dataset,variant,format,content_sha256,raw_bytes,gzip_bytes FROM measured) GROUP BY ALL)
SELECT * FROM sizes JOIN unique_sizes USING(dataset,variant,format);
CREATE TABLE zoom_summary AS SELECT dataset,variant,factor,format,logical_z,COUNT(*) tiles,
 SUM(raw_bytes) raw_bytes,SUM(gzip_bytes) gzip_bytes,SUM(features) features,SUM(vertices) vertices,
 SUM(fragments) fragments FROM measured GROUP BY ALL;
CREATE TABLE savings AS SELECT a.dataset,a.variant,a.factor,a.format,a.tiles,
 100.*(1.-a.raw_bytes::DOUBLE/m.raw_bytes) raw_saving_pct,
 100.*(1.-a.gzip_bytes::DOUBLE/m.gzip_bytes) gzip_saving_pct
 FROM archive_summary a JOIN archive_summary m USING(dataset,variant) WHERE m.format='mvt' AND a.format!='mvt';
CREATE VIEW all_blocks AS
SELECT dataset,variant,format,logical_z,z,x,y,SUM(raw_bytes) raw_bytes,SUM(gzip_bytes) gzip_bytes,
 SUM(features) features,SUM(vertices) vertices,SUM(fragments) fragments,
 SUM(repeated_vertices) repeated_vertices FROM measured WHERE variant!='standard' GROUP BY ALL
UNION ALL
SELECT dataset,'standard4',format,logical_z,CAST(logical_z-1 AS BIGINT),CAST(floor(x/2) AS BIGINT),CAST(floor(y/2) AS BIGINT),
 SUM(raw_bytes),SUM(gzip_bytes),SUM(features),SUM(vertices),SUM(fragments),NULL
 FROM measured WHERE variant='standard' AND logical_z>=1 GROUP BY ALL
UNION ALL
SELECT dataset,'standard16',format,logical_z,CAST(logical_z-2 AS BIGINT),CAST(floor(x/4) AS BIGINT),CAST(floor(y/4) AS BIGINT),
 SUM(raw_bytes),SUM(gzip_bytes),SUM(features),SUM(vertices),SUM(fragments),NULL
 FROM measured WHERE variant='standard' AND logical_z>=2 GROUP BY ALL;
CREATE VIEW matched_blocks AS
SELECT s.dataset,s.format,s.logical_z,s.z,s.x,s.y,f.factor,
 s.raw_bytes standard_raw,a.raw_bytes aggregated_raw,d.raw_bytes dense_raw,
 s.gzip_bytes standard_gzip,a.gzip_bytes aggregated_gzip,d.gzip_bytes dense_gzip,
 s.features standard_features,a.features aggregated_features,d.features dense_features,
 s.vertices standard_vertices,a.vertices aggregated_vertices,d.vertices dense_vertices,
 s.fragments standard_fragments,a.fragments aggregated_fragments,d.fragments dense_fragments,
 a.repeated_vertices aggregated_repeated_vertices,d.repeated_vertices dense_repeated_vertices
FROM (VALUES (4),(16)) f(factor)
JOIN all_blocks s ON s.variant='standard'||f.factor
JOIN all_blocks a ON a.dataset=s.dataset AND a.format=s.format AND a.logical_z=s.logical_z AND a.z=s.z AND a.x=s.x AND a.y=s.y AND a.variant='aggregated'||f.factor
JOIN all_blocks d ON d.dataset=s.dataset AND d.format=s.format AND d.logical_z=s.logical_z AND d.z=s.z AND d.x=s.x AND d.y=s.y AND d.variant='dense'||f.factor;
CREATE TABLE decomposition_zoom AS
SELECT dataset,factor,format,logical_z,compression_state,COUNT(*) blocks,
 SUM(s) standard_bytes,SUM(a) aggregated_bytes,SUM(d) dense_bytes,
 SUM(s-a) aggregation_reduction_bytes,SUM(a-d) regeneration_reduction_bytes,SUM(s-d) total_reduction_bytes,
 100.*SUM(s-a)/SUM(s) aggregation_pct,100.*SUM(a-d)/SUM(s) regeneration_pct,100.*SUM(s-d)/SUM(s) total_pct
FROM (SELECT *, 'raw' compression_state,standard_raw s,aggregated_raw a,dense_raw d FROM matched_blocks
 UNION ALL SELECT *, 'gzip6',standard_gzip,aggregated_gzip,dense_gzip FROM matched_blocks) GROUP BY ALL;
CREATE TABLE decomposition AS SELECT dataset,factor,format,compression_state,SUM(blocks) blocks,
 SUM(standard_bytes) standard_bytes,SUM(aggregated_bytes) aggregated_bytes,SUM(dense_bytes) dense_bytes,
 SUM(aggregation_reduction_bytes) aggregation_reduction_bytes,SUM(regeneration_reduction_bytes) regeneration_reduction_bytes,
 SUM(total_reduction_bytes) total_reduction_bytes,
 100.*SUM(aggregation_reduction_bytes)/SUM(standard_bytes) aggregation_pct,
 100.*SUM(regeneration_reduction_bytes)/SUM(standard_bytes) regeneration_pct,
 100.*SUM(total_reduction_bytes)/SUM(standard_bytes) total_pct
FROM decomposition_zoom GROUP BY ALL;
CREATE TABLE coverage AS WITH support AS (
SELECT s.dataset,f.factor,s.logical_z,
 COUNT(*) standard_blocks,COUNT(a.x) aggregated_blocks,COUNT(d.x) dense_blocks,
 COUNT(*) FILTER(WHERE a.x IS NOT NULL AND d.x IS NOT NULL) matched_blocks
FROM (VALUES (4),(16)) f(factor) JOIN all_blocks s ON s.variant='standard'||f.factor AND s.format='mvt'
LEFT JOIN all_blocks a ON a.dataset=s.dataset AND a.variant='aggregated'||f.factor AND a.format=s.format AND a.logical_z=s.logical_z AND a.z=s.z AND a.x=s.x AND a.y=s.y
LEFT JOIN all_blocks d ON d.dataset=s.dataset AND d.variant='dense'||f.factor AND d.format=s.format AND d.logical_z=s.logical_z AND d.z=s.z AND d.x=s.x AND d.y=s.y GROUP BY ALL),
dense_totals AS (SELECT d.dataset,f.factor,d.logical_z,COUNT(*) dense_total_blocks
 FROM (VALUES (4),(16)) f(factor) JOIN all_blocks d ON d.variant='dense'||f.factor AND d.format='mvt' GROUP BY ALL)
SELECT s.*,d.dense_total_blocks,d.dense_total_blocks-s.dense_blocks dense_only_blocks,
 s.standard_blocks-s.matched_blocks excluded_standard_blocks
FROM support s JOIN dense_totals d USING(dataset,factor,logical_z);
CREATE TABLE content_summary AS
SELECT a.dataset,a.variant,a.logical_z,SUM(i.instances) feature_instances,COUNT(DISTINCT i.source_id) unique_source_features,
 SUM(i.instances)-COUNT(DISTINCT i.source_id) repeated_instances
FROM addresses a JOIN feature_ids i USING(dataset,variant,payload_key) GROUP BY ALL;
CREATE VIEW matched_source_ids AS
SELECT b.dataset,b.factor,b.logical_z,'aggregated' regime,COUNT(DISTINCT i.source_id) unique_sources
FROM matched_blocks b JOIN addresses a ON a.dataset=b.dataset AND a.variant='aggregated'||b.factor AND a.z=b.z AND a.x=b.x AND a.y=b.y
JOIN feature_ids i ON i.dataset=a.dataset AND i.variant=a.variant AND i.payload_key=a.payload_key WHERE b.format='mvt' GROUP BY ALL
UNION ALL
SELECT b.dataset,b.factor,b.logical_z,'dense',COUNT(DISTINCT i.source_id)
FROM matched_blocks b JOIN addresses a ON a.dataset=b.dataset AND a.variant='dense'||b.factor AND a.z=b.z AND a.x=b.x AND a.y=b.y
JOIN feature_ids i ON i.dataset=a.dataset AND i.variant=a.variant AND i.payload_key=a.payload_key WHERE b.format='mvt' GROUP BY ALL;
CREATE TABLE content_differences AS WITH differences AS (SELECT dataset,factor,SUM(standard_features) standard_features,
 SUM(aggregated_features) aggregated_features,SUM(dense_features) dense_features,
 SUM(standard_vertices) standard_vertices,SUM(aggregated_vertices) aggregated_vertices,SUM(dense_vertices) dense_vertices,
 SUM(aggregated_fragments) aggregated_fragments,SUM(dense_fragments) dense_fragments,
 SUM(aggregated_repeated_vertices) aggregated_repeated_vertices,SUM(dense_repeated_vertices) dense_repeated_vertices
FROM matched_blocks WHERE format='mvt' GROUP BY ALL),
identities AS (SELECT dataset,factor,SUM(unique_sources) FILTER(WHERE regime='aggregated') aggregated_source_features_zoom_sum,
 SUM(unique_sources) FILTER(WHERE regime='dense') dense_source_features_zoom_sum FROM matched_source_ids GROUP BY ALL)
SELECT *,aggregated_features-aggregated_source_features_zoom_sum aggregated_repeated_instances,
 dense_features-dense_source_features_zoom_sum dense_repeated_instances
FROM differences JOIN identities USING(dataset,factor);
CREATE TABLE stream_summary AS
WITH frames_ AS (SELECT dataset,variant,format,SUM(frame_bytes) frame_bytes,COUNT(*) layers FROM frames GROUP BY ALL),
streams_ AS (SELECT dataset,variant,format,SUM(payload_bytes) payload_bytes,SUM(num_values) num_values,COUNT(*) streams FROM streams GROUP BY ALL)
SELECT *,num_values::DOUBLE/streams values_per_stream,(frame_bytes-payload_bytes)::DOUBLE/frame_bytes structural_share,
 payload_bytes::DOUBLE/NULLIF(num_values,0) payload_bytes_per_value FROM frames_ JOIN streams_ USING(dataset,variant,format);
CREATE TABLE layer_summary AS SELECT dataset,variant,format,layer,SUM(frame_bytes) frame_bytes,COUNT(*) unique_payload_layers FROM frames GROUP BY ALL;
CREATE TABLE attribute_summary AS SELECT a.dataset,a.variant,p.format,p.source_type,p.imported_type,SUM(p.occurrences) occurrences
FROM addresses a JOIN attributes p USING(dataset,variant,payload_key) GROUP BY ALL;
CREATE TABLE validation_summary AS SELECT a.dataset,a.variant,v.format,COUNT(*) checked_addresses,
 SUM(CASE WHEN v.roundtrip_passed THEN 0 ELSE 1 END) differing_addresses,
 SUM(v.source_features-v.imported_features) import_feature_difference,
 SUM(v.source_vertices-v.imported_vertices) import_vertex_difference
FROM addresses a JOIN validation v USING(dataset,variant,payload_key) GROUP BY ALL;
CREATE TABLE aggregation_validation AS SELECT dataset,variant,COUNT(*) blocks,SUM(children) children,
 SUM(features) features,SUM(vertices) vertices,SUM(fragments) fragments,BOOL_AND(passed) passed FROM equivalence GROUP BY ALL;
CREATE TABLE vertex_bins AS SELECT m.variant, m.format,
 CASE WHEN m.vertices<100 THEN '<100' WHEN m.vertices<1000 THEN '100--999'
 WHEN m.vertices<10000 THEN '1,000--9,999' WHEN m.vertices<100000 THEN '10,000--99,999' ELSE '100,000+' END vertex_bin,
 COUNT(*) tiles,SUM(m.raw_bytes) mlt_raw_bytes,SUM(v.raw_bytes) mvt_raw_bytes,
 SUM(m.gzip_bytes) mlt_gzip_bytes,SUM(v.gzip_bytes) mvt_gzip_bytes,
 100.*(1.-SUM(m.raw_bytes)::DOUBLE/SUM(v.raw_bytes)) raw_saving_pct,
 100.*(1.-SUM(m.gzip_bytes)::DOUBLE/SUM(v.gzip_bytes)) gzip_saving_pct
FROM measured m JOIN measured v ON m.dataset=v.dataset AND m.variant=v.variant AND m.z=v.z AND m.x=v.x AND m.y=v.y AND v.format='mvt'
WHERE m.format!='mvt' GROUP BY ALL;
CREATE TABLE bytes_per_vertex AS SELECT dataset,variant,format,
 raw_bytes::DOUBLE/NULLIF(vertices,0) raw_bytes_per_vertex,gzip_bytes::DOUBLE/NULLIF(vertices,0) gzip_bytes_per_vertex,
 raw_bytes::DOUBLE/NULLIF(features,0) raw_bytes_per_feature,gzip_bytes::DOUBLE/NULLIF(features,0) gzip_bytes_per_feature
FROM archive_summary;
