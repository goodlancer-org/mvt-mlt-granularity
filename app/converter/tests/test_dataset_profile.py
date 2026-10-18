import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.dataset_profile import (
    build_dataset_profile,
    dataset_profiles_dir,
    resolve_dataset_profile,
    sanitize_dataset_id,
    save_dataset_profile,
    validate_dataset_profile,
    validate_topology_equality,
)


def test_dataset_profile_paths_are_dataset_scoped(tmp_path):
    assert dataset_profiles_dir(tmp_path) == tmp_path / "datasets"
    assert sanitize_dataset_id("Netherlands Amsterdam") == "netherlands_amsterdam"


def test_build_dataset_profile_creates_draft_profile():
    profile = build_dataset_profile(
        "amsterdam",
        "/data/sources/amsterdam.gpkg",
        "gpkg",
        {"layers": [{"name": "roads", "geometry_type": "LineString", "fields": [{"name": "class"}]}]},
    )

    assert profile["dataset"]["id"] == "amsterdam"
    assert profile["output"]["container"] == "pmtiles"
    assert profile["tile_layers"][0]["source_layers"] == ["roads"]


def test_profile_can_be_persisted_and_resolved(tmp_path):
    profile = build_dataset_profile(
        "amsterdam",
        "/data/sources/amsterdam.gpkg",
        "gpkg",
        {"layers": [{"name": "roads", "geometry_type": "LineString", "fields": [{"name": "class"}]}]},
    )
    saved_path = save_dataset_profile(profile, tmp_path)
    assert saved_path.exists()
    assert resolve_dataset_profile("amsterdam", tmp_path) == saved_path
    resolved = resolve_dataset_profile("amsterdam", tmp_path, create_if_missing=True)
    assert resolved is not None
    assert resolved.exists()


def test_validate_dataset_profile_rejects_legacy_mbtiles_and_missing_fields():
    invalid = {
        "dataset": {"id": "amsterdam"},
        "output": {"container": "mbtiles", "tile_format": "mvt"},
        "tile_layers": [],
    }
    with pytest.raises(ValueError, match="PMTiles|container"):
        validate_dataset_profile(invalid)

    valid = {
        "dataset": {"id": "amsterdam"},
        "output": {"container": "pmtiles", "tile_format": "mvt", "encoding_pair": ["mvt", "mlt"]},
        "source": {"normalization": {"stable_feature_id_strategy": "source_primary_key"}},
        "tile_layers": [{"id": "roads", "source_layers": ["roads"]}],
    }
    validate_dataset_profile(valid)


def test_validate_topology_equality_rejects_mismatched_feature_ids():
    mvt = {
        "0/0/0": {"roads": {"feature_ids": [101, 102], "feature_count": 2}},
        "0/0/1": {"water": {"feature_ids": [201], "feature_count": 1}},
    }
    mlt = {
        "0/0/0": {"roads": {"feature_ids": [101, 103], "feature_count": 2}},
        "0/0/1": {"water": {"feature_ids": [201], "feature_count": 1}},
    }

    with pytest.raises(ValueError, match="feature_ids|topology"):
        validate_topology_equality(mvt, mlt)

    validate_topology_equality(mvt, mvt)
