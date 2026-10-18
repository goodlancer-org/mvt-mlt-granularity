import sys
import json
import sqlite3
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import normalization


def test_normalization_command_selects_and_clips_bounds(tmp_path):
    cmd = normalization.build_normalization_command(
        source_path=tmp_path / "raw.gpkg",
        output_path=tmp_path / "canonical.partial.gpkg",
        bounds=[4.84, 52.34, 4.95, 52.4],
        normalized_crs="EPSG:3857",
    )

    assert cmd[:4] == ["ogr2ogr", "-progress", "-f", "GPKG"]
    assert "-t_srs" in cmd and "EPSG:3857" in cmd
    assert "-spat_srs" in cmd and "-spat" in cmd
    assert cmd[cmd.index("-clipsrc") + 1] == "spat_extent"
    assert "-clipdst" not in cmd
    assert "SPATIAL_INDEX=YES" in cmd


def test_normalization_fingerprint_separates_profile_from_tile_generation():
    base = normalization.normalization_fingerprint(
        source_sha256="source",
        profile_plan={"normalization": {"stable_feature_id_strategy": "source"}},
        bounds="0,0,1,1",
        normalized_crs="EPSG:3857",
        gdal_version="GDAL 1",
    )
    changed_bounds = normalization.normalization_fingerprint(
        source_sha256="source",
        profile_plan={"normalization": {"stable_feature_id_strategy": "source"}},
        bounds="0,0,2,2",
        normalized_crs="EPSG:3857",
        gdal_version="GDAL 1",
    )

    assert base != changed_bounds
    assert base["bounds"] == ["0.0", "0.0", "1.0", "1.0"]


def test_partial_gpkg_is_not_reused_as_cache_hit(tmp_path, monkeypatch):
    source = tmp_path / "source.gpkg"
    source.write_bytes(b"source")
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir()
    (normalized_dir / "demo.partial.gpkg").write_bytes(b"partial")

    monkeypatch.setattr(normalization, "_gdal_version", lambda: "GDAL test")
    monkeypatch.setattr(
        normalization,
        "validate_normalized_gpkg",
        lambda *args, **kwargs: {
            "layers": [{"name": "roads", "feature_count": None}],
            "layer_count": 1,
            "spatial_index_count": 1,
        },
    )
    monkeypatch.setattr(normalization, "inspect_gpkg", lambda path: {"layers": [{"name": "roads", "feature_count": None}]})

    calls = []

    def runner(cmd):
        calls.append(cmd)
        with closing(sqlite3.connect(cmd[4])) as con, con:
            con.execute('CREATE TABLE sample(id INTEGER)')
        return {"exit_code": 0, "combined_output": ""}

    result = normalization.normalize_source_to_gpkg(
        dataset_name="demo",
        source_path=source,
        normalized_dir=normalized_dir,
        source_format="gpkg",
        profile_plan={"normalization": {"stable_feature_id_strategy": "source"}},
        bounds=None,
        run_command=runner,
    )

    assert calls
    assert result["artifact_status"] == "generated"
    assert result["path"].name == "demo.gpkg"
    assert not (normalized_dir / "demo.partial.gpkg").exists()
    assert result["manifest"]["unknown_feature_counts"] == ["roads"]


def test_publish_normalized_gpkg_verifies_final_file(tmp_path):
    partial = tmp_path / "demo.partial.gpkg"
    final = tmp_path / "demo.gpkg"
    with closing(sqlite3.connect(partial)) as con, con:
        con.execute('CREATE TABLE sample(id INTEGER)')

    normalization._publish_normalized_gpkg(partial, final)

    assert final.read_bytes().startswith(b"SQLite format 3\x00")
    assert not partial.exists()


def test_validation_closes_sqlite_before_publish(tmp_path, monkeypatch):
    partial, final = tmp_path/'partial.gpkg', tmp_path/'final.gpkg'
    with closing(sqlite3.connect(partial)) as con, con:
        con.executescript("CREATE TABLE gpkg_contents(table_name TEXT,data_type TEXT);"
                          "CREATE TABLE gpkg_geometry_columns(table_name TEXT,column_name TEXT,srs_id INTEGER);")
    monkeypatch.setattr(normalization, 'inspect_gpkg', lambda path: {'layers': [{'name': 'places'}]})
    normalization.validate_normalized_gpkg(partial)
    normalization._publish_normalized_gpkg(partial, final)
    assert final.is_file()


def test_cached_normalized_gpkg_requires_matching_manifest(tmp_path, monkeypatch):
    source = tmp_path / "source.gpkg"
    source.write_bytes(b"source")
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir()
    gpkg = normalized_dir / "demo.gpkg"
    gpkg.write_bytes(b"complete")

    monkeypatch.setattr(normalization, "_gdal_version", lambda: "GDAL test")
    fingerprint = normalization.normalization_fingerprint(
        source_sha256=normalization.sha256_file(source),
        profile_plan={},
        bounds=None,
        normalized_crs="EPSG:3857",
        gdal_version="GDAL test",
    )
    (normalized_dir / "demo.normalization.json").write_text(json.dumps({
        "fingerprint": fingerprint,
        "gpkg_sha256": "sha",
        "bounds": ["0", "0", "1", "1"],
        "normalized_crs": "EPSG:3857",
        "stable_id_strategy": "source",
    }), encoding="utf-8")
    monkeypatch.setattr(normalization, "validate_normalized_gpkg", lambda *args, **kwargs: {"layers": []})
    calls = []

    result = normalization.normalize_source_to_gpkg(
        dataset_name="demo",
        source_path=source,
        normalized_dir=normalized_dir,
        source_format="gpkg",
        profile_plan={},
        bounds=None,
        run_command=lambda cmd: calls.append(cmd),
    )

    assert result["artifact_status"] == "reused_from_cache"
    assert calls == []


def test_normalized_dir_file_collision_migrates_legacy_sqlite(tmp_path, monkeypatch):
    source = tmp_path / "source.gpkg"
    source.write_bytes(b"source")
    normalized_dir = tmp_path / "normalized" / "demo"
    normalized_dir.parent.mkdir(parents=True, exist_ok=True)
    normalized_dir.write_bytes(b"SQLite format 3\x00legacy")

    monkeypatch.setattr(normalization, "_gdal_version", lambda: "GDAL test")
    monkeypatch.setattr(
        normalization,
        "validate_normalized_gpkg",
        lambda *args, **kwargs: {
            "layers": [{"name": "roads", "feature_count": 1}],
            "layer_count": 1,
            "spatial_index_count": 1,
        },
    )

    def runner(cmd):
        Path(cmd[4]).write_bytes(b"SQLite format 3\x00new")
        return {"exit_code": 0, "combined_output": ""}

    result = normalization.normalize_source_to_gpkg(
        dataset_name="demo",
        source_path=source,
        normalized_dir=normalized_dir,
        source_format="gpkg",
        profile_plan={},
        bounds=None,
        run_command=runner,
    )

    assert normalized_dir.is_dir()
    assert result["path"].name == "demo.gpkg"


def test_normalized_dir_file_collision_non_sqlite_raises(tmp_path):
    normalized_dir = tmp_path / "normalized" / "bad"
    normalized_dir.parent.mkdir(parents=True, exist_ok=True)
    normalized_dir.write_text("not a gpkg", encoding="utf-8")

    try:
        normalization._ensure_normalized_dir(
            normalized_dir=normalized_dir,
            dataset_name="bad",
            progress_callback=None,
        )
    except RuntimeError as exc:
        assert "not a SQLite/GPKG" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for non-SQLite collision")


def test_publish_normalized_gpkg_recovers_empty_directory_target(tmp_path):
    partial = tmp_path / "demo.partial.gpkg"
    target = tmp_path / "demo.gpkg"
    partial.write_bytes(b"SQLite format 3\x00payload")
    target.mkdir()

    normalization._publish_normalized_gpkg(partial, target)

    assert target.is_file()
    assert target.read_bytes().startswith(b"SQLite format 3\x00")
    assert not partial.exists()


def test_publish_normalized_gpkg_fails_on_nonempty_directory_target(tmp_path):
    partial = tmp_path / "demo.partial.gpkg"
    target = tmp_path / "demo.gpkg"
    partial.write_bytes(b"SQLite format 3\x00payload")
    target.mkdir()
    (target / "leftover.txt").write_text("x", encoding="utf-8")

    try:
        normalization._publish_normalized_gpkg(partial, target)
    except RuntimeError as exc:
        assert "non-empty directory" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for non-empty gpkg directory target")
