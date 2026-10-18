import sys
import json
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import gdal_tiles


def test_gdal_stage_b_uses_one_direct_pmtiles_job_for_variant(tmp_path, monkeypatch):
    commands = []

    monkeypatch.setattr(
        gdal_tiles,
        "_ogrinfo_preflight",
        lambda **kwargs: {
            "raw": "{}",
            "layers_with_counts": [
                {"name": "normalized_buildings", "feature_count": 2},
                {"name": "normalized_structures", "feature_count": 3},
            ],
        },
    )

    def fake_run_command(cmd, **kwargs):
        commands.append(cmd)
        return {
            "exit_code": 0,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "time_seconds": 1.0,
            "time_ms": 1000,
            "peak_memory_mb": 12.0,
            "combined_output": "",
            "canceled": False,
        }

    monkeypatch.setattr(gdal_tiles, "_run_command", fake_run_command)
    monkeypatch.setattr(
        gdal_tiles,
        "_scan_mvt_archive",
        lambda path, expected_extent: {
            "tile_count": 1,
            "feature_count": 5,
            "vertex_count": 5,
            "layers": {"buildings": {"feature_count": 5}},
            "extent_validation": {
                "checked_tiles": 1,
                "expected_extent": expected_extent,
                "passed": True,
                "mismatch_count": 0,
                "mismatches": [],
            },
            "time_seconds": 0.01,
        },
    )
    monkeypatch.setattr(
        gdal_tiles,
        "transcode_mvt_pmtiles_to_mlt",
        lambda mvt, mlt, validation_mode="fast": {
            "tile_count": 1,
            "validation": {
                "mode": validation_mode,
                "lightweight": {"tile_count": 1, "min_tileid": 0, "max_tileid": 0},
                "full": None,
                "validation_seconds": 0.0,
            },
        },
    )
    monkeypatch.setattr(gdal_tiles, "get_output_size", lambda path: 123)
    monkeypatch.setattr(gdal_tiles, "_sha256", lambda path: "sha")

    conversions = gdal_tiles.run_gdal_dense_pipeline(
        name="demo",
        source_path=tmp_path / "canonical.gpkg",
        output_dir=tmp_path,
        logs_dir=tmp_path,
        profile_plan={
            "tile_layers": [
                {
                    "id": "buildings",
                    "source_layers": ["normalized_buildings", "normalized_structures"],
                    "zoom": {"min": 4, "max": 14},
                }
            ]
        },
        analysis={"layers": []},
        min_zoom=0,
        max_zoom=14,
        bounds="-1,-1,1,1",
        variants=[{"key": "dense4", "detail_offset": 1, "extent": 8192}],
        validation_mode="fast",
        tile_limits_mode="experimental_unlimited",
    )

    assert len(commands) == 2  # One MVT tiling job, then lossless PMTiles repack.
    cmd = commands[0]
    assert cmd[0] == "ogr2ogr" and cmd[cmd.index("-f") + 1] == "MVT"
    assert "FORMAT=MBTILES" in cmd
    configuration = json.loads(next(item[5:] for item in cmd if item.startswith("CONF=")))
    assert "normalized_buildings" in configuration
    assert "normalized_structures" in configuration
    assert commands[1][0] == "ogr2ogr"
    assert commands[1][1].endswith("demo_dense4_mvt.pmtiles")
    assert commands[1][2].endswith(".work.mbtiles")
    assert any("EXTENT=8192" == item for item in cmd)
    conf = cmd[cmd.index("-dsco") + 1:] if "-dsco" in cmd else []
    assert "dense4_mvt" in conversions
    assert conversions["dense4_mvt"]["detail_offset"] == 1


def test_dense_variant_definitions_are_sparse_pyramid_contract():
    assert [(v["key"], v["detail_offset"], v["extent"]) for v in gdal_tiles.DENSE_VARIANTS] == [
        ("standard", 0, 4096),
        ("dense4", 1, 8192),
        ("dense16", 2, 16384),
    ]


def test_ogrinfo_preflight_keeps_unknown_feature_count_unknown(monkeypatch, tmp_path):
    calls = []

    def fake_run_command(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["ogrinfo", "-ro", "-json"]:
            return {
                "exit_code": 0,
                "combined_output": '{"driverShortName":"GPKG","layers":[{"name":"roads","featureCount":-1}]}',
            }
        return {
            "exit_code": 0,
            "combined_output": '{"layers":[{"name":"roads","featureCount":-1}]}',
        }

    monkeypatch.setattr(gdal_tiles, "_run_command", fake_run_command)

    with sqlite3.connect(tmp_path / "canonical.gpkg") as con:
        con.execute('CREATE TABLE gpkg_geometry_columns(table_name TEXT, srs_id INTEGER, z INTEGER, m INTEGER)')
        con.execute("INSERT INTO gpkg_geometry_columns VALUES ('roads',3857,0,0)")

    result = gdal_tiles._ogrinfo_preflight(
        source_path=tmp_path / "canonical.gpkg",
        progress_callback=None,
        log_progress=None,
    )

    assert result["layers_with_counts"] == [{"name": "roads", "feature_count": None}]
    assert result["total_features"] == 0


def test_tile_limits_mode_safe_replaces_unlimited_defaults():
    size, features = gdal_tiles._resolve_tile_limits(
        tile_limits_mode="safe",
        max_size=gdal_tiles.DEFAULT_MAX_TILE_BYTES,
        max_features=gdal_tiles.DEFAULT_MAX_TILE_FEATURES,
    )

    assert size == gdal_tiles.SAFE_MAX_TILE_BYTES
    assert features == gdal_tiles.SAFE_MAX_TILE_FEATURES
