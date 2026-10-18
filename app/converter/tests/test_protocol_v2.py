import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.protocol_v2 import build_protocol_v2
from src.protocol_summary import synthesize_protocol_v2
from src.protocol_v2 import write_protocol_v2


def test_build_protocol_v2_matches_design_contract():
    dataset = {
        "id": "amsterdam",
        "title": "Amsterdam",
        "source_format": "osm_pbf",
        "source_sha256": "abc123" * 8,
        "crs": "EPSG:4326",
    }
    profile = {
        "version": 1,
        "dataset": {"id": "amsterdam"},
        "output": {"container": "pmtiles", "encoding_pair": ["mvt", "mlt"]},
        "source": {"normalization": {"stable_feature_id_strategy": "source_primary_key"}},
        "tile_layers": [{"id": "roads", "source_layers": ["lines"]}],
    }
    profile_path = "app/converter/profiles/datasets/amsterdam.yaml"
    tools = {
        "planetiler": "0.8.0",
        "gdal": "3.8.0",
        "mlt_transcoder": "1.0.0",
        "pmtiles": "1.2.0",
        "geomaps_revision": "deadbeef",
    }
    topology = {
        "topology_id": 1,
        "min_zoom": 0,
        "max_zoom": 14,
        "layer_count": 1,
        "logical_feature_count": 42,
        "feature_instance_count": 120,
        "vertex_count": 3030,
    }
    outputs = {
        "mvt": {
            "path": "data/output/amsterdam.mvt.pmtiles",
            "archive_sha256": "mvtsha",
            "archive_bytes": 1000,
            "tile_count": 10,
            "tile_stored_bytes": 900,
            "tile_encoded_bytes": 500,
            "tile_compression": "gzip",
            "generation_method": "canonical_tiler",
        },
        "mlt": {
            "path": "data/output/amsterdam.mlt.pmtiles",
            "archive_sha256": "mltsha",
            "archive_bytes": 700,
            "tile_count": 10,
            "tile_stored_bytes": 600,
            "tile_encoded_bytes": 350,
            "tile_compression": "gzip",
            "generation_method": "mvt_to_mlt_transcode",
        },
    }
    validation = {
        "source_analysis_complete": True,
        "profile_valid": True,
        "stable_ids_available": True,
        "mvt_archive_valid": True,
        "mlt_archive_valid": True,
        "tile_coordinates_equal": True,
        "layer_names_equal": True,
        "feature_counts_equal": True,
        "feature_ids_equal": True,
        "semantic_classes_equal": True,
        "workload_generation_complete": True,
        "research_ready": True,
    }
    zoom_summary = [{"zoom": 8, "tile_count": 10}]
    layer_summary = [{"layer": "roads", "semantic_category": "transportation", "semantic_type": "residential_road"}]
    workload_summary = [{"scenario_name": "cold", "step_index": 0, "new_tile_count": 3}]

    protocol = build_protocol_v2(
        dataset=dataset,
        profile=profile,
        profile_path=profile_path,
        tools=tools,
        topology=topology,
        outputs=outputs,
        validation=validation,
        zoom_summary=zoom_summary,
        layer_summary=layer_summary,
        workload_summary=workload_summary,
    )

    assert protocol["version"] == "2.0"
    assert protocol["dataset"]["id"] == "amsterdam"
    assert protocol["profile"]["sha256"]
    assert protocol["profile"]["path"] == profile_path
    assert protocol["tools"]["planetiler"] == "0.8.0"
    assert set(protocol["outputs"]) == {"mvt", "mlt"}
    assert protocol["validation"]["research_ready"] is True
    assert protocol["zoom_summary"][0]["zoom"] == 8
    assert protocol["layer_summary"][0]["layer"] == "roads"
    assert protocol["workload_summary"][0]["scenario_name"] == "cold"


def test_synthesize_protocol_v2_leaves_v2_payload_unchanged(tmp_path):
    protocol = {
        "version": "2.0",
        "dataset": {"id": "amsterdam"},
        "profile": {"version": 1, "sha256": "abc", "origin": "saved", "path": "x"},
        "outputs": {"mvt": {}, "mlt": {}},
    }

    assert synthesize_protocol_v2(protocol) == protocol


def test_write_protocol_v2_writes_json(tmp_path):
    protocol = {"version": "2.0", "dataset": {"id": "amsterdam"}, "profile": {"version": 1, "sha256": "abc", "origin": "saved", "path": "x"}, "outputs": {"mvt": {}, "mlt": {}}, "validation": {}, "zoom_summary": [], "layer_summary": [], "workload_summary": [], "topology": {"topology_id": 1, "min_zoom": 0, "max_zoom": 0, "layer_count": 0, "logical_feature_count": None, "feature_instance_count": 0, "vertex_count": 0}, "tools": {}}
    path = write_protocol_v2(protocol, tmp_path / "amsterdam.json")
    assert path.exists()
