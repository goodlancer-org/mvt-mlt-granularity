"""Where a PMTiles archive has data, read from its tile directory (standard library only).

An archive's header carries bounds and a center, but a conversion that was not given an extent writes the whole world and (0, 0): the
Netherlands archives did, so a viewer that trusts the header opens on empty ocean. The tile directory cannot lie about this: it lists
exactly which tiles exist. This reads that list (PMTiles spec version 3) and returns the bounds of the tiles at the deepest zoom.

Nothing here reads tile payloads, only the header and the directories, so it is fast even for archives of hundreds of megabytes.
"""

from __future__ import annotations

import gzip
import math
import struct
from functools import lru_cache
from pathlib import Path

_HEADER_BYTES = 127
_COMPRESSION_NONE, _COMPRESSION_GZIP = 1, 2


def _varint(buf, pos):
    result = shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7


def _directory(raw):
    """Decode one directory into [(tile_id, offset, length, run_length)]."""
    count, pos = _varint(raw, 0)
    tile_ids, run_lengths, lengths, offsets = [], [], [], []
    last = 0
    for _ in range(count):
        delta, pos = _varint(raw, pos)
        last += delta
        tile_ids.append(last)
    for _ in range(count):
        value, pos = _varint(raw, pos)
        run_lengths.append(value)
    for _ in range(count):
        value, pos = _varint(raw, pos)
        lengths.append(value)
    for i in range(count):
        value, pos = _varint(raw, pos)
        if value == 0 and i > 0:
            offsets.append(offsets[i - 1] + lengths[i - 1])        # contiguous with the previous entry
        else:
            offsets.append(value - 1)
    return list(zip(tile_ids, offsets, lengths, run_lengths))


def _rotate(n, x, y, rx, ry):
    if ry == 0:
        if rx == 1:
            x, y = n - 1 - x, n - 1 - y
        x, y = y, x
    return x, y


def tile_id_to_zxy(tile_id):
    """Position of a PMTiles tile id on the Hilbert curve -> (z, x, y)."""
    acc = 0
    for z in range(32):
        tiles_at_z = (1 << z) * (1 << z)
        if acc + tiles_at_z > tile_id:
            n, t, x, y, s = 1 << z, tile_id - acc, 0, 0, 1
            while s < n:
                rx = 1 & (t // 2)
                ry = 1 & (t ^ rx)
                x, y = _rotate(s, x, y, rx, ry)
                x += s * rx
                y += s * ry
                t //= 4
                s *= 2
            return z, x, y
        acc += tiles_at_z
    raise ValueError(f"tile id out of range: {tile_id}")


def _inflate(data, compression):
    if compression == _COMPRESSION_GZIP:
        return gzip.decompress(data)
    if compression == _COMPRESSION_NONE:
        return data
    raise ValueError(f"unsupported directory compression: {compression}")


def _entries(path):
    """Yield (tile_id, absolute_offset, length, run_length) for every tile entry of the archive, following leaf directories."""
    with open(path, "rb") as handle:
        header = handle.read(_HEADER_BYTES)
        if header[:7] != b"PMTiles" or header[7] != 3:
            raise ValueError(f"not a PMTiles v3 archive: {path}")
        root_offset, root_length, _, _, leaf_offset, _ = struct.unpack_from("<6Q", header, 8)
        tile_data_offset = struct.unpack_from("<Q", header, 56)[0]
        internal_compression = header[97]

        def read(offset, length):
            handle.seek(offset)
            return _directory(_inflate(handle.read(length), internal_compression))

        pending = [read(root_offset, root_length)]
        while pending:
            for tile_id, offset, length, run_length in pending.pop():
                if run_length == 0:                                    # a pointer to a leaf directory
                    pending.append(read(leaf_offset + offset, length))
                    continue
                yield tile_id, tile_data_offset + offset, length, run_length


def tiles_by_zoom(path):
    """{zoom: [(x, y), ...]} for every tile the archive holds."""
    found = {}
    for tile_id, _offset, _length, run_length in _entries(path):
        for tid in range(tile_id, tile_id + run_length):
            z, x, y = tile_id_to_zxy(tid)
            found.setdefault(z, []).append((x, y))
    return found


def tile_ranges(path):
    """{(absolute_offset, length): (z, x, y)}: which tile a byte range of the archive is. Tiles in a run share one range."""
    ranges = {}
    for tile_id, offset, length, run_length in _entries(path):
        for tid in range(tile_id, tile_id + run_length):
            ranges[(offset, length)] = tile_id_to_zxy(tid)
    return ranges


def _lon(x, z):
    return x / (1 << z) * 360.0 - 180.0


def _lat(y, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (1 << z)))))


def _extent(path):
    tiles = tiles_by_zoom(path)
    if not tiles:
        return None
    z = max(tiles)                                                      # the deepest zoom has the tightest fit
    xs = [x for x, _ in tiles[z]]
    ys = [y for _, y in tiles[z]]
    return [_lon(min(xs), z), _lat(max(ys) + 1, z), _lon(max(xs) + 1, z), _lat(min(ys), z)]


@lru_cache(maxsize=64)
def _cached_extent(path, mtime_ns, size):
    return _extent(path)


def archive_extent(path):
    """[min_lon, min_lat, max_lon, max_lat] of the tiles at the archive's deepest zoom, or None for an empty or unreadable archive.

    Cached per file, modification time and size: rapid Windows rewrites can share
    a modification timestamp while changing the tile directory.
    """
    path = Path(path)
    try:
        stat = path.stat()
        return _cached_extent(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, IndexError, struct.error):
        return None
