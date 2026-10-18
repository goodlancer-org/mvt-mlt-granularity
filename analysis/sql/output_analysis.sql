WITH

/* ============================================================
   1. Итог по dataset / variant
   ============================================================ */
variant_summary AS (
    SELECT
        dataset_name,
        variant,
        density_factor,

        COUNT(*) AS tile_count,
        SUM(feature_instances) AS feature_count,
        SUM(vertex_count) AS vertex_count,

        ROUND(AVG(feature_instances), 2) AS avg_features_per_tile,
        ROUND(AVG(vertex_count), 2) AS avg_vertices_per_tile,
        ROUND(AVG(layer_count), 2) AS avg_layers_per_tile,

        ROUND(SUM(mvt_raw_bytes) / 1048576.0, 3) AS mvt_raw_mib,
        ROUND(SUM(mvt_gzip_bytes) / 1048576.0, 3) AS mvt_gzip_mib,
        ROUND(SUM(mlt_raw_bytes) / 1048576.0, 3) AS mlt_raw_mib,
        ROUND(SUM(mlt_gzip_bytes) / 1048576.0, 3) AS mlt_gzip_mib,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mvt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mvt_gzip_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_raw_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mlt_raw_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_gzip_bytes), 0)
            ),
            3
        ) AS mlt_after_gzip_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS total_mlt_gzip_saving_pct,

        ROUND(
            SUM(mvt_raw_bytes) * 1.0 /
            NULLIF(SUM(feature_instances), 0),
            3
        ) AS mvt_raw_bytes_per_feature,

        ROUND(
            SUM(mlt_raw_bytes) * 1.0 /
            NULLIF(SUM(feature_instances), 0),
            3
        ) AS mlt_raw_bytes_per_feature,

        ROUND(
            SUM(mvt_raw_bytes) * 1.0 /
            NULLIF(SUM(vertex_count), 0),
            4
        ) AS mvt_raw_bytes_per_vertex,

        ROUND(
            SUM(mlt_raw_bytes) * 1.0 /
            NULLIF(SUM(vertex_count), 0),
            4
        ) AS mlt_raw_bytes_per_vertex,

        -- [ADDED] gzip bytes per vertex (Table tab:bpv)
        ROUND(SUM(mvt_gzip_bytes) * 1.0 / NULLIF(SUM(vertex_count), 0), 4) AS mvt_gzip_bytes_per_vertex,
        ROUND(SUM(mlt_gzip_bytes) * 1.0 / NULLIF(SUM(vertex_count), 0), 4) AS mlt_gzip_bytes_per_vertex

    FROM v_tile_comparison
    GROUP BY
        dataset_name,
        variant,
        density_factor
),


/* ============================================================
   2. Gain dense4 / dense16 против standard
   ============================================================ */
variant_compression AS (
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
    GROUP BY dataset_name, variant
),

dense_gain AS (
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
    GROUP BY dataset_name
),


/* ============================================================
   3. Feature-density buckets
   ============================================================ */
feature_binned AS (
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

        dataset_name,          -- [ADDED]
        variant,               -- [ADDED]
        feature_instances,
        vertex_count,
        layer_count,
        mvt_raw_bytes,
        mvt_gzip_bytes,
        mlt_raw_bytes,
        mlt_gzip_bytes

    FROM v_tile_comparison
),

feature_summary AS (
    SELECT
        feature_bin,

        COUNT(*) AS tile_count,

        ROUND(AVG(feature_instances), 2) AS avg_features,
        ROUND(AVG(vertex_count), 2) AS avg_vertices,
        ROUND(AVG(layer_count), 2) AS avg_layers,
        ROUND(AVG(mvt_raw_bytes) / 1024.0, 2) AS avg_mvt_raw_kib,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mvt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mvt_gzip_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_raw_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mlt_raw_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_gzip_bytes), 0)
            ),
            3
        ) AS mlt_after_gzip_saving_pct

    FROM feature_binned
    GROUP BY feature_bin
),


/* ============================================================
   4. Vertex-density buckets
   ============================================================ */
vertex_binned AS (
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

        dataset_name,          -- [ADDED]
        variant,               -- [ADDED]
        feature_instances,
        vertex_count,
        layer_count,
        mvt_raw_bytes,
        mvt_gzip_bytes,
        mlt_raw_bytes,
        mlt_gzip_bytes

    FROM v_tile_comparison
),

vertex_summary AS (
    SELECT
        vertex_bin,

        COUNT(*) AS tile_count,

        ROUND(AVG(vertex_count), 2) AS avg_vertices,
        ROUND(AVG(feature_instances), 2) AS avg_features,
        ROUND(AVG(layer_count), 2) AS avg_layers,
        ROUND(AVG(mvt_raw_bytes) / 1024.0, 2) AS avg_mvt_raw_kib,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mvt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mvt_gzip_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_raw_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mlt_raw_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_gzip_bytes), 0)
            ),
            3
        ) AS mlt_after_gzip_saving_pct

    FROM vertex_binned
    GROUP BY vertex_bin
),


/* ============================================================
   5. Layer count
   ============================================================ */
layer_count_summary AS (
    SELECT
        layer_count,
        COUNT(*) AS tile_count,

        ROUND(AVG(feature_instances), 2) AS avg_features,
        ROUND(AVG(vertex_count), 2) AS avg_vertices,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_raw_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_bytes), 0)
            ),
            3
        ) AS mlt_raw_saving_pct,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_gzip_bytes) * 1.0 /
                NULLIF(SUM(mvt_gzip_bytes), 0)
            ),
            3
        ) AS mlt_after_gzip_saving_pct

    FROM v_tile_comparison
    GROUP BY layer_count
),


/* ============================================================
   6. Layer compression
   ============================================================ */
layer_compression AS (
    SELECT
        dataset_name,
        variant,
        density_factor,
        layer_name,

        COUNT(*) AS tile_count,
        SUM(feature_instances) AS feature_count,
        SUM(vertex_count) AS vertex_count,

        ROUND(
            SUM(mvt_raw_layer_bytes) / 1048576.0,
            3
        ) AS mvt_raw_mib,

        ROUND(
            SUM(mlt_raw_layer_bytes) / 1048576.0,
            3
        ) AS mlt_raw_mib,

        ROUND(
            100.0 * (
                1.0 -
                SUM(mlt_raw_layer_bytes) * 1.0 /
                NULLIF(SUM(mvt_raw_layer_bytes), 0)
            ),
            3
        ) AS mlt_raw_saving_pct,

        SUM(mvt_key_count) AS mvt_key_count,
        SUM(mvt_value_count) AS mvt_value_count,

        SUM(mlt_stream_count) AS mlt_stream_count,

        ROUND(
            SUM(mlt_stream_payload_bytes) / 1048576.0,
            4
        ) AS stream_payload_mib,

        ROUND(
            SUM(mlt_stream_overhead_bytes) / 1048576.0,
            4
        ) AS stream_overhead_mib,

        ROUND(
            100.0 *
            SUM(mlt_stream_overhead_bytes) /
            NULLIF(
                SUM(mlt_stream_payload_bytes) +
                SUM(mlt_stream_overhead_bytes),
                0
            ),
            3
        ) AS stream_overhead_pct,

        SUM(mlt_parse_errors) AS parse_error_count

    FROM v_tile_layer_comparison
    WHERE mlt_raw_layer_bytes IS NOT NULL

    GROUP BY
        dataset_name,
        variant,
        density_factor,
        layer_name
),


/* ============================================================
   7. Geometry composition
   ============================================================ */
geometry_summary AS (
    SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,
        s.geometry_type,

        SUM(s.feature_instances) AS feature_count,
        SUM(s.vertex_count) AS vertex_count,

        ROUND(
            SUM(s.vertex_count) * 1.0 /
            NULLIF(SUM(s.feature_instances), 0),
            2
        ) AS vertices_per_feature

    FROM tile_layer_stats s
    JOIN maps m
        ON m.id = s.map_id

    GROUP BY
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,
        s.geometry_type
),


/* ============================================================
   8. MLT streams — агрегат
   ============================================================ */
mlt_stream_summary AS (
    SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,

        s.stream_role,
        s.logical_encoding,
        s.physical_encoding,

        COUNT(*) AS stream_count,
        SUM(s.num_values) AS value_count,

        ROUND(
            SUM(s.payload_bytes) / 1048576.0,
            4
        ) AS payload_mib,

        ROUND(
            SUM(s.header_bytes) / 1048576.0,
            4
        ) AS header_mib,

        ROUND(
            SUM(s.total_bytes) / 1048576.0,
            4
        ) AS total_mib,

        ROUND(
            AVG(s.num_values),
            2
        ) AS avg_values_per_stream,

        ROUND(
            SUM(s.total_bytes) * 1.0 /
            NULLIF(SUM(s.num_values), 0),
            4
        ) AS bytes_per_value,

        ROUND(
            100.0 *
            SUM(s.header_bytes) /
            NULLIF(SUM(s.total_bytes), 0),
            3
        ) AS header_overhead_pct

    FROM mlt_streams s
    JOIN archives a
        ON a.id = s.archive_id
    JOIN maps m
        ON m.id = a.map_id

    GROUP BY
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.stream_role,
        s.logical_encoding,
        s.physical_encoding
),


/* ============================================================
   9. MLT streams — по layer
   ============================================================ */
mlt_stream_layer_summary AS (
    SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,

        s.stream_role,
        s.logical_encoding,
        s.physical_encoding,

        COUNT(*) AS stream_count,
        SUM(s.num_values) AS value_count,

        ROUND(
            SUM(s.total_bytes) / 1024.0,
            3
        ) AS total_kib,

        ROUND(
            SUM(s.total_bytes) * 1.0 /
            NULLIF(SUM(s.num_values), 0),
            4
        ) AS bytes_per_value

    FROM mlt_streams s
    JOIN archives a
        ON a.id = s.archive_id
    JOIN maps m
        ON m.id = a.map_id

    GROUP BY
        m.dataset_name,
        m.variant,
        m.density_factor,
        s.layer_name,
        s.stream_role,
        s.logical_encoding,
        s.physical_encoding
),


/* ============================================================
   10. Parse diagnostics
   ============================================================ */
parse_diagnostics AS (
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
        ml.parse_error
),


/* ============================================================
   11. [ADDED] Vertex bins per dataset and variant (pooled bins are
       dominated by Natural Earth; Results 4.2 needs the split)
   ============================================================ */
vertex_summary_by_dataset AS (
    SELECT
        dataset_name,
        variant,
        vertex_bin,
        COUNT(*) AS tile_count,
        ROUND(AVG(vertex_count), 2) AS avg_vertices,
        ROUND(AVG(feature_instances), 2) AS avg_features,
        ROUND(100.0 * (1.0 - SUM(mlt_raw_bytes) * 1.0 / NULLIF(SUM(mvt_raw_bytes), 0)), 3) AS mlt_raw_saving_pct,
        ROUND(100.0 * (1.0 - SUM(mlt_gzip_bytes) * 1.0 / NULLIF(SUM(mvt_gzip_bytes), 0)), 3) AS mlt_after_gzip_saving_pct
    FROM vertex_binned
    GROUP BY dataset_name, variant, vertex_bin
),


/* ============================================================
   12. [ADDED] Stream totals per dataset and variant, with parse
       coverage. Used for Table tab:streams and the decomposition
       of the gain into metadata and value encoding.
   ============================================================ */
stream_totals AS (
    SELECT
        m.dataset_name,
        m.variant,
        m.density_factor,
        COUNT(*) AS stream_count,
        SUM(s.num_values) AS value_count,
        SUM(s.header_bytes) AS header_bytes,
        SUM(s.payload_bytes) AS payload_bytes,
        SUM(s.total_bytes) AS stream_bytes
    FROM mlt_streams s
    JOIN archives a ON a.id = s.archive_id
    JOIN maps m ON m.id = a.map_id
    GROUP BY m.dataset_name, m.variant, m.density_factor
),

layer_parse_coverage AS (
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
    GROUP BY m.dataset_name, m.variant
),


/* ============================================================
   13. [ADDED] Savings by logical zoom (stored z + detail offset),
       so that variants can be compared at the same level of detail
   ============================================================ */
logical_zoom_summary AS (
    SELECT
        dataset_name,
        variant,
        density_factor,
        z + CASE density_factor WHEN 1 THEN 0 WHEN 4 THEN 1 WHEN 16 THEN 2 END AS logical_z,
        COUNT(*) AS tile_count,
        ROUND(AVG(vertex_count), 2) AS avg_vertices_per_tile,
        SUM(mvt_raw_bytes) AS mvt_raw_bytes,
        SUM(mvt_gzip_bytes) AS mvt_gzip_bytes,
        SUM(mlt_raw_bytes) AS mlt_raw_bytes,
        SUM(mlt_gzip_bytes) AS mlt_gzip_bytes,
        ROUND(100.0 * (1.0 - SUM(mlt_raw_bytes) * 1.0 / NULLIF(SUM(mvt_raw_bytes), 0)), 3) AS mlt_raw_saving_pct,
        ROUND(100.0 * (1.0 - SUM(mlt_gzip_bytes) * 1.0 / NULLIF(SUM(mvt_gzip_bytes), 0)), 3) AS mlt_after_gzip_saving_pct
    FROM v_tile_comparison
    GROUP BY dataset_name, variant, density_factor, logical_z
)





/* ============================================================
   FINAL JSON
   ============================================================ */
SELECT json_object(

    'variant_summary',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'density_factor', density_factor,

                'tiles', tile_count,
                'features', feature_count,
                'vertices', vertex_count,

                'avg_features_per_tile', avg_features_per_tile,
                'avg_vertices_per_tile', avg_vertices_per_tile,
                'avg_layers_per_tile', avg_layers_per_tile,

                'mvt_raw_mib', mvt_raw_mib,
                'mvt_gzip_mib', mvt_gzip_mib,
                'mlt_raw_mib', mlt_raw_mib,
                'mlt_gzip_mib', mlt_gzip_mib,

                'mvt_gzip_saving_pct', mvt_gzip_saving_pct,
                'mlt_raw_saving_pct', mlt_raw_saving_pct,
                'mlt_after_gzip_saving_pct', mlt_after_gzip_saving_pct,
                'total_mlt_gzip_saving_pct', total_mlt_gzip_saving_pct,

                'mvt_raw_bytes_per_feature', mvt_raw_bytes_per_feature,
                'mlt_raw_bytes_per_feature', mlt_raw_bytes_per_feature,

                'mvt_raw_bytes_per_vertex', mvt_raw_bytes_per_vertex,
                'mlt_raw_bytes_per_vertex', mlt_raw_bytes_per_vertex,
                'mvt_gzip_bytes_per_vertex', mvt_gzip_bytes_per_vertex,
                'mlt_gzip_bytes_per_vertex', mlt_gzip_bytes_per_vertex
            )
        )
        FROM (
            SELECT *
            FROM variant_summary
            ORDER BY dataset_name, density_factor
        )
    ),


    'dense_gain_vs_standard',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,

                'standard_mlt_raw_pct',
                    ROUND(standard_raw_pct, 3),

                'dense4_mlt_raw_pct',
                    ROUND(dense4_raw_pct, 3),

                'dense16_mlt_raw_pct',
                    ROUND(dense16_raw_pct, 3),

                'dense4_raw_gain_pp',
                    ROUND(dense4_raw_pct - standard_raw_pct, 3),

                'dense16_raw_gain_pp',
                    ROUND(dense16_raw_pct - standard_raw_pct, 3),

                'standard_after_gzip_pct',
                    ROUND(standard_after_gzip_pct, 3),

                'dense4_after_gzip_pct',
                    ROUND(dense4_after_gzip_pct, 3),

                'dense16_after_gzip_pct',
                    ROUND(dense16_after_gzip_pct, 3),

                'dense4_after_gzip_gain_pp',
                    ROUND(
                        dense4_after_gzip_pct -
                        standard_after_gzip_pct,
                        3
                    ),

                'dense16_after_gzip_gain_pp',
                    ROUND(
                        dense16_after_gzip_pct -
                        standard_after_gzip_pct,
                        3
                    )
            )
        )
        FROM (
            SELECT *
            FROM dense_gain
            ORDER BY dataset_name
        )
    ),


    'zoom_analysis',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'density_factor', density_factor,
                'z', z,

                'tiles', tile_count,
                'features', feature_instances,
                'vertices', vertex_count,

                'avg_features_per_tile',
                    ROUND(avg_features_per_tile, 2),

                'avg_vertices_per_tile',
                    ROUND(avg_vertices_per_tile, 2),

                'mvt_raw_mib',
                    ROUND(mvt_raw_bytes / 1048576.0, 3),

                'mlt_raw_mib',
                    ROUND(mlt_raw_bytes / 1048576.0, 3),

                'mlt_raw_saving_pct',
                    ROUND(
                        mlt_raw_saving_fraction * 100.0,
                        3
                    ),

                'mlt_after_gzip_saving_pct',
                    ROUND(
                        mlt_after_gzip_saving_fraction * 100.0,
                        3
                    ),

                'mvt_gzip_saving_pct',
                    ROUND(
                        mvt_gzip_saving_fraction * 100.0,
                        3
                    )
            )
        )
        FROM (
            SELECT *
            FROM v_zoom_analysis
            ORDER BY
                dataset_name,
                density_factor,
                z
        )
    ),


    'compression_by_feature_count',
    (
        SELECT json_group_array(
            json_object(
                'feature_bin', feature_bin,
                'tiles', tile_count,

                'avg_features', avg_features,
                'avg_vertices', avg_vertices,
                'avg_layers', avg_layers,
                'avg_mvt_raw_kib', avg_mvt_raw_kib,

                'mvt_gzip_saving_pct',
                    mvt_gzip_saving_pct,

                'mlt_raw_saving_pct',
                    mlt_raw_saving_pct,

                'mlt_after_gzip_saving_pct',
                    mlt_after_gzip_saving_pct
            )
        )
        FROM (
            SELECT *
            FROM feature_summary
            ORDER BY feature_bin
        )
    ),


    'compression_by_vertex_count',
    (
        SELECT json_group_array(
            json_object(
                'vertex_bin', vertex_bin,
                'tiles', tile_count,

                'avg_vertices', avg_vertices,
                'avg_features', avg_features,
                'avg_layers', avg_layers,
                'avg_mvt_raw_kib', avg_mvt_raw_kib,

                'mvt_gzip_saving_pct',
                    mvt_gzip_saving_pct,

                'mlt_raw_saving_pct',
                    mlt_raw_saving_pct,

                'mlt_after_gzip_saving_pct',
                    mlt_after_gzip_saving_pct
            )
        )
        FROM (
            SELECT *
            FROM vertex_summary
            ORDER BY vertex_bin
        )
    ),


    'compression_by_layer_count',
    (
        SELECT json_group_array(
            json_object(
                'layer_count', layer_count,
                'tiles', tile_count,

                'avg_features', avg_features,
                'avg_vertices', avg_vertices,

                'mlt_raw_saving_pct',
                    mlt_raw_saving_pct,

                'mlt_after_gzip_saving_pct',
                    mlt_after_gzip_saving_pct
            )
        )
        FROM (
            SELECT *
            FROM layer_count_summary
            ORDER BY layer_count
        )
    ),


    'layer_compression',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'density_factor', density_factor,
                'layer', layer_name,

                'tiles', tile_count,
                'features', feature_count,
                'vertices', vertex_count,

                'mvt_raw_mib', mvt_raw_mib,
                'mlt_raw_mib', mlt_raw_mib,
                'mlt_raw_saving_pct', mlt_raw_saving_pct,

                'mvt_key_count', mvt_key_count,
                'mvt_value_count', mvt_value_count,

                'mlt_stream_count', mlt_stream_count,

                'stream_payload_mib',
                    stream_payload_mib,

                'stream_overhead_mib',
                    stream_overhead_mib,

                'stream_overhead_pct',
                    stream_overhead_pct,

                'parse_error_count',
                    parse_error_count
            )
        )
        FROM (
            SELECT *
            FROM layer_compression
            ORDER BY
                dataset_name,
                density_factor,
                mvt_raw_mib DESC
        )
    ),


    'geometry_composition',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'density_factor', density_factor,
                'layer', layer_name,

                'geometry_type', geometry_type,
                'features', feature_count,
                'vertices', vertex_count,
                'vertices_per_feature',
                    vertices_per_feature
            )
        )
        FROM (
            SELECT *
            FROM geometry_summary
            ORDER BY
                dataset_name,
                density_factor,
                layer_name,
                feature_count DESC
        )
    ),


    'mlt_stream_summary',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'density_factor', density_factor,

                'stream_role', stream_role,
                'logical_encoding', logical_encoding,
                'physical_encoding', physical_encoding,

                'stream_count', stream_count,
                'value_count', value_count,

                'payload_mib', payload_mib,
                'header_mib', header_mib,
                'total_mib', total_mib,

                'avg_values_per_stream',
                    avg_values_per_stream,

                'bytes_per_value',
                    bytes_per_value,

                'header_overhead_pct',
                    header_overhead_pct
            )
        )
        FROM (
            SELECT *
            FROM mlt_stream_summary
            ORDER BY
                dataset_name,
                density_factor,
                total_mib DESC
        )
    ),


    'mlt_streams_by_layer',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'density_factor', density_factor,
                'layer', layer_name,

                'stream_role', stream_role,
                'logical_encoding', logical_encoding,
                'physical_encoding', physical_encoding,

                'stream_count', stream_count,
                'value_count', value_count,

                'total_kib', total_kib,
                'bytes_per_value', bytes_per_value
            )
        )
        FROM (
            SELECT *
            FROM mlt_stream_layer_summary
            ORDER BY
                dataset_name,
                density_factor,
                layer_name,
                total_kib DESC
        )
    ),


    'mlt_parse_diagnostics',
    (
        SELECT json_group_array(
            json_object(
                'dataset', dataset_name,
                'variant', variant,
                'layer', layer_name,
                'frame_tag', frame_tag,
                'parse_error', parse_error,
                'occurrences', occurrence_count
            )
        )
        FROM (
            SELECT *
            FROM parse_diagnostics
            ORDER BY
                dataset_name,
                variant,
                layer_name
        )
    ),


    -- [ADDED]
    'compression_by_vertex_count_per_dataset',
    (
        SELECT json_group_array(json_object(
            'dataset', dataset_name, 'variant', variant, 'vertex_bin', vertex_bin,
            'tiles', tile_count, 'avg_vertices', avg_vertices, 'avg_features', avg_features,
            'mlt_raw_saving_pct', mlt_raw_saving_pct,
            'mlt_after_gzip_saving_pct', mlt_after_gzip_saving_pct))
        FROM (SELECT * FROM vertex_summary_by_dataset ORDER BY dataset_name, variant, vertex_bin)
    ),

    'stream_totals',
    (
        SELECT json_group_array(json_object(
            'dataset', t.dataset_name, 'variant', t.variant, 'density_factor', t.density_factor,
            'streams', t.stream_count, 'values', t.value_count,
            'header_bytes', t.header_bytes, 'payload_bytes', t.payload_bytes, 'stream_bytes', t.stream_bytes,
            'values_per_stream', ROUND(t.value_count * 1.0 / NULLIF(t.stream_count, 0), 2),
            'layer_frames', c.layer_frames, 'failed_frames', c.failed_frames,
            'frame_bytes', c.frame_bytes, 'failed_frame_bytes', c.failed_frame_bytes))
        FROM stream_totals t
        LEFT JOIN layer_parse_coverage c
            ON c.dataset_name = t.dataset_name AND c.variant = t.variant
        ORDER BY t.dataset_name, t.density_factor
    ),

    'logical_zoom_analysis',
    (
        SELECT json_group_array(json_object(
            'dataset', dataset_name, 'variant', variant, 'density_factor', density_factor,
            'logical_z', logical_z, 'tiles', tile_count, 'avg_vertices_per_tile', avg_vertices_per_tile,
            'mvt_raw_bytes', mvt_raw_bytes, 'mvt_gzip_bytes', mvt_gzip_bytes,
            'mlt_raw_bytes', mlt_raw_bytes, 'mlt_gzip_bytes', mlt_gzip_bytes,
            'mlt_raw_saving_pct', mlt_raw_saving_pct,
            'mlt_after_gzip_saving_pct', mlt_after_gzip_saving_pct))
        FROM (SELECT * FROM logical_zoom_summary ORDER BY dataset_name, logical_z, density_factor)
    )


) AS compression_report_json;