import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DEFAULT_CONFIG, load_config, validate_research_formats


def test_default_research_matrix_is_pmtiles_only():
    combos = [(combo["tile_format"], combo["container"]) for combo in DEFAULT_CONFIG["formats"]]
    assert combos == [("mvt", "pmtiles"), ("mlt", "pmtiles")]


def test_default_tmp_dir_points_to_host_mounted_scratch():
    cfg = load_config()
    assert cfg["tmp_dir"] == "/scratch"


def test_config_rejects_legacy_mbtiles_matrix():
    try:
        validate_research_formats([
            {"tile_format": "mvt", "container": "mbtiles"},
            {"tile_format": "mlt", "container": "pmtiles"},
        ])
        raise AssertionError("MBTiles matrix should have been rejected")
    except ValueError:
        pass

    cfg = load_config()
    assert cfg["formats"] == [
        {"tile_format": "mvt", "container": "pmtiles"},
        {"tile_format": "mlt", "container": "pmtiles"},
    ]
