"""A dataset whose profile has no output bounds still reports where its data is, taken from the archive's tile directory.

The Netherlands archives carry whole-world header bounds and a (0, 0) center; the viewer needs the real extent to open on the data.
An extent supplied by the profile must win over the one read from the tiles.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import src.api as api
from test_pmtiles_extent import _lat, _lon, _write_archive


def _protocol(mlt="demo_mlt.pmtiles", mvt="demo_mvt.pmtiles", extent=None):
    return {"dataset": {"id": "demo", "extent": extent}, "outputs": {"mlt": {"path": mlt}, "mvt": {"path": mvt}}}


def test_fills_the_extent_from_the_tiles_when_the_profile_gave_none(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)
    _write_archive(tmp_path / "demo_mlt.pmtiles", [(3, 4, 2), (14, 8438, 5418), (14, 8466, 5426)])

    protocol = api._with_data_extent(_protocol())

    west, south, east, north = protocol["dataset"]["extent"]
    assert (west, east) == (_lon(8438, 14), _lon(8467, 14))
    assert (north, south) == (_lat(5418, 14), _lat(5427, 14))
    assert protocol["dataset"]["extent_source"] == "tile directory"


def test_an_extent_from_the_profile_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)
    _write_archive(tmp_path / "demo_mlt.pmtiles", [(14, 8438, 5418)])
    given = [9.15, 47.05, 9.5, 47.3]

    protocol = api._with_data_extent(_protocol(extent=given))

    assert protocol["dataset"]["extent"] == given
    assert "extent_source" not in protocol["dataset"]


def test_falls_back_to_the_mvt_archive_when_the_mlt_one_is_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)
    (tmp_path / "demo_mlt.pmtiles").write_bytes(b"broken")
    _write_archive(tmp_path / "demo_mvt.pmtiles", [(14, 8438, 5418)])

    assert api._with_data_extent(_protocol())["dataset"]["extent"] is not None


def test_a_missing_archive_leaves_the_protocol_as_it_was(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)

    protocol = api._with_data_extent(_protocol())

    assert not protocol["dataset"]["extent"]


def test_a_protocol_without_outputs_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)

    assert api._with_data_extent({"dataset": {"id": "demo"}}) == {"dataset": {"id": "demo"}}
