"""A range request for a tile must map back to that tile.

The harness sees HTTP range requests against a PMTiles archive. Mapping (offset, length) back to z/x/y through the archive's own
directory is what lets the stored size of exactly that tile be the ground truth for the bytes the browser received.
"""

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from src.pmtiles_extent import tile_ranges
from test_pmtiles_extent import _write_archive


def test_every_tile_range_maps_to_its_tile(tmp_path):
    tiles = [(3, 4, 2), (5, 17, 11), (5, 18, 11), (5, 17, 12)]
    path = tmp_path / "a.pmtiles"
    _write_archive(path, tiles)

    ranges = tile_ranges(path)

    assert sorted(ranges.values()) == sorted(tiles)
    assert all(length == 10 for (_, length) in ranges)            # the synthetic archive stores 10 bytes per tile


def test_offsets_are_absolute_in_the_file(tmp_path):
    path = tmp_path / "a.pmtiles"
    _write_archive(path, [(5, 17, 11)])
    header = path.read_bytes()[:127]
    tile_data_offset = struct.unpack_from("<Q", header, 56)[0]

    (offset, _length), _zxy = next(iter(tile_ranges(path).items()))

    assert offset == tile_data_offset + 0
