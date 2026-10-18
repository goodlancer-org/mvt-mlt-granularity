"""Where an archive has data, read from its tile directory.

The Netherlands archives were written with whole-world bounds and a (0, 0) center, so a viewer that trusts the header opens on empty
ocean. The tile directory lists exactly which tiles exist, so the extent is read from there. The synthetic archives below are built
byte by byte (header, gzip-compressed root and leaf directories) so the test needs no PMTiles library.
"""

import gzip
import math
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pmtiles_extent import archive_extent, tile_id_to_zxy, tiles_by_zoom


# ── an independent writer, straight from the PMTiles v3 spec ───────────────────────────────────────────────────────────────────

def _put_varint(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _rotate(n, x, y, rx, ry):
    if ry == 0:
        if rx == 1:
            x, y = n - 1 - x, n - 1 - y
        x, y = y, x
    return x, y


def zxy_to_tile_id(z, x, y):
    acc = sum(4 ** i for i in range(z))
    n, d, s = 1 << z, 0, (1 << z) // 2
    while s > 0:
        rx = 1 if (x & s) > 0 else 0
        ry = 1 if (y & s) > 0 else 0
        d += s * s * ((3 * rx) ^ ry)
        x, y = _rotate(n, x, y, rx, ry)
        s //= 2
    return acc + d


def _serialize_directory(entries):
    """entries: [(tile_id, offset, length, run_length)] sorted by tile id."""
    out = bytearray(_put_varint(len(entries)))
    last = 0
    for tile_id, *_ in entries:
        out += _put_varint(tile_id - last)
        last = tile_id
    for _, _, _, run in entries:
        out += _put_varint(run)
    for _, _, length, _ in entries:
        out += _put_varint(length)
    prev_offset = prev_length = None
    for _, offset, length, _ in entries:
        out += _put_varint(0 if prev_offset is not None and offset == prev_offset + prev_length else offset + 1)
        prev_offset, prev_length = offset, length
    return gzip.compress(bytes(out))


def _write_archive(path, tiles, leaf_for=()):
    """tiles: [(z, x, y)] -> a PMTiles v3 file whose header claims the WHOLE WORLD, like the Netherlands archives.

    Tiles listed in `leaf_for` go into a leaf directory instead of the root, to exercise directory pointers.
    """
    by_id = sorted((zxy_to_tile_id(*t), t) for t in tiles)
    leaf_ids = {zxy_to_tile_id(*t) for t in leaf_for}
    entries = []
    for i, (tid, _) in enumerate(by_id):
        entries.append((tid, i * 10, 10, 1))
    root_entries = [e for e in entries if e[0] not in leaf_ids]
    leaf_entries = [e for e in entries if e[0] in leaf_ids]
    leaf_blob = _serialize_directory(leaf_entries) if leaf_entries else b""
    if leaf_entries:
        root_entries.append((leaf_entries[0][0], 0, len(leaf_blob), 0))      # run_length 0: a pointer to the leaf directory
        root_entries.sort()
    root_blob = _serialize_directory(root_entries)
    root_offset = 127
    leaf_offset = root_offset + len(root_blob)
    header = bytearray(127)
    header[0:7] = b"PMTiles"
    header[7] = 3
    struct.pack_into("<6Q", header, 8, root_offset, len(root_blob), 0, 0, leaf_offset, len(leaf_blob))
    tile_data_offset = leaf_offset + len(leaf_blob)
    struct.pack_into("<Q", header, 56, tile_data_offset)
    header[97] = 2                                                           # internal compression: gzip
    header[100], header[101] = 0, 14
    struct.pack_into("<4i", header, 102, -1800000000, -850511287, 1800000000, 850511287)   # the whole world, as the header says
    Path(path).write_bytes(bytes(header) + root_blob + leaf_blob + b"x" * (10 * len(entries)))


def _lon(x, z):
    return x / 2 ** z * 360 - 180


def _lat(y, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


# ── tests ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_tile_ids_map_back_to_their_tile():
    for z, x, y in [(0, 0, 0), (1, 1, 0), (3, 4, 2), (10, 538, 359), (14, 8458, 5422), (14, 8466, 5426)]:
        assert tile_id_to_zxy(zxy_to_tile_id(z, x, y)) == (z, x, y)


def test_every_tile_of_a_small_pyramid_round_trips():
    for z in range(0, 6):
        for x in range(2 ** z):
            for y in range(2 ** z):
                assert tile_id_to_zxy(zxy_to_tile_id(z, x, y)) == (z, x, y)


def test_reads_the_tiles_an_archive_holds(tmp_path):
    tiles = [(3, 4, 2), (4, 8, 5), (5, 17, 11), (5, 18, 11), (5, 17, 12)]
    path = tmp_path / "a.pmtiles"
    _write_archive(path, tiles)

    found = tiles_by_zoom(path)

    assert {z: sorted(v) for z, v in found.items()} == {3: [(4, 2)], 4: [(8, 5)], 5: [(17, 11), (17, 12), (18, 11)]}


def test_follows_leaf_directories(tmp_path):
    tiles = [(6, 34, 22), (6, 35, 22), (6, 36, 23), (6, 37, 23)]
    path = tmp_path / "leafy.pmtiles"
    _write_archive(path, tiles, leaf_for=tiles[2:])

    assert sorted(tiles_by_zoom(path)[6]) == sorted((x, y) for _, x, y in tiles)


def test_extent_is_the_bounds_of_the_deepest_zoom_not_the_header(tmp_path):
    # the header of this archive says the whole world; the tiles say a small area
    tiles = [(3, 4, 2), (14, 8438, 5418), (14, 8466, 5426), (14, 8450, 5420)]
    path = tmp_path / "world_header.pmtiles"
    _write_archive(path, tiles)

    west, south, east, north = archive_extent(path)

    assert west == _lon(8438, 14) and east == _lon(8467, 14)
    assert north == _lat(5418, 14) and south == _lat(5427, 14)
    assert 5.3 < west < east < 6.2 and 51.7 < south < north < 52.0       # the Nijmegen area, not the world


def test_extent_of_an_unreadable_or_empty_archive_is_none(tmp_path):
    garbage = tmp_path / "garbage.pmtiles"
    garbage.write_bytes(b"not an archive at all")
    assert archive_extent(garbage) is None
    assert archive_extent(tmp_path / "missing.pmtiles") is None


def test_extent_follows_the_file_when_it_is_rewritten(tmp_path):
    path = tmp_path / "grows.pmtiles"
    _write_archive(path, [(5, 17, 11)])
    first = archive_extent(path)
    first_mtime = path.stat().st_mtime_ns

    _write_archive(path, [(5, 17, 11), (5, 25, 11)])
    os.utime(path, ns=(first_mtime, first_mtime))
    second = archive_extent(path)

    assert second[2] > first[2]                                           # not served from a stale cache entry
