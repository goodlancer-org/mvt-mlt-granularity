"""Tests for serving MBTiles tiles.

MBTiles is measured against PMTiles, so any per-request overhead the server
adds lands in the results as if it were a property of the container format.
Opening a fresh SQLite connection for every tile was exactly that.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api import tile_db_connection


def _make_mbtiles(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER,"
        " tile_row INTEGER, tile_data BLOB)"
    )
    conn.execute("INSERT INTO tiles VALUES (10, 525, 336, ?)", (b"tile-bytes",))
    conn.commit()
    conn.close()
    return path


def test_reuses_one_connection_across_tile_reads(tmp_path):
    archive = _make_mbtiles(tmp_path / "amsterdam_mvt.mbtiles")

    first = tile_db_connection(archive)
    second = tile_db_connection(archive)

    assert first is second


def test_keeps_separate_connections_per_archive(tmp_path):
    mvt = _make_mbtiles(tmp_path / "amsterdam_mvt.mbtiles")
    mlt = _make_mbtiles(tmp_path / "amsterdam_mlt.mbtiles")

    assert tile_db_connection(mvt) is not tile_db_connection(mlt)


def test_the_reused_connection_can_still_read_tiles(tmp_path):
    archive = _make_mbtiles(tmp_path / "amsterdam_mvt.mbtiles")

    conn = tile_db_connection(archive)
    for _ in range(3):
        row = conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (10, 525, 336),
        ).fetchone()
        assert bytes(row[0]) == b"tile-bytes"
