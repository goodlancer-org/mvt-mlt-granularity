from __future__ import annotations

"""PMTiles MVT/MLT measurements for the paper pipeline.

Runtime dependencies for full analysis:
    duckdb, pyarrow, pandas, matplotlib, mapbox-vector-tile
Optional decompression dependencies, needed only when the corresponding PMTiles
compression is encountered:
    brotli, zstandard

Semantic content and geometry complexity are decoded from MVT. The paired MLT
archive is measured independently for PMTiles physical layout and payload sizes,
and stable MLT v1 frames are also inspected structurally down to column/stream
metadata (value counts, encodings, and wire byte sizes). Tile-coordinate equality
is validated before MVT semantics are attributed to the MLT pair.
"""

import gzip
import io
import json
import math
import os
import re
import sqlite3
import struct
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

SCHEMA_VERSION = 3
PMTILES_HEADER_SIZE = 127
PMTILES_MAGIC = b"PMTiles"
PMTILES_VERSION = 3

FORMAT_MVT = "MVT"
FORMAT_MLT = "MLT"
TILE_TYPE_NAMES = {
    0: "UNKNOWN",
    1: "MVT",
    2: "PNG",
    3: "JPEG",
    4: "WEBP",
    5: "AVIF",
    6: "MLT",
}
COMPRESSION_NAMES = {
    0: "UNKNOWN",
    1: "NONE",
    2: "GZIP",
    3: "BROTLI",
    4: "ZSTD",
}
GEOMETRY_NAMES = {
    0: "UNKNOWN",
    1: "POINT",
    2: "LINESTRING",
    3: "POLYGON",
}


MLT_V1_TAG = 0x01

MLT_COLUMN_TYPES = {
    0: "Id",
    1: "OptId",
    2: "LongId",
    3: "OptLongId",
    4: "Geometry",
    10: "Bool",
    11: "OptBool",
    16: "Int32",
    17: "OptInt32",
    18: "UInt32",
    19: "OptUInt32",
    20: "Int64",
    21: "OptInt64",
    22: "UInt64",
    23: "OptUInt64",
    24: "Float",
    25: "OptFloat",
    26: "Double",
    27: "OptDouble",
    28: "String",
    29: "OptString",
    30: "SharedDict",
}

MLT_STREAM_CATEGORY_NAMES = {
    0: "Present",
    1: "Data",
    2: "Offset",
    3: "Length",
}
MLT_STREAM_SUBTYPE_NAMES = {
    0: {0: "Present"},
    1: {0: "None", 1: "SingleDictionary", 2: "SharedDictionary", 3: "Vertex", 4: "Morton", 5: "FSST"},
    2: {0: "Vertex", 1: "Index", 2: "String", 3: "Key"},
    3: {0: "VarBinary", 1: "Geometries", 2: "Parts", 3: "Rings", 4: "Triangles", 5: "Symbol", 6: "Dictionary"},
}
MLT_LOGICAL_ENCODING_NAMES = {
    (0, 0): "None",
    (1, 0): "Delta",
    (1, 3): "DeltaRLE",
    (2, 0): "ComponentwiseDelta",
    (3, 0): "RLE",
    (4, 1): "MortonDelta",
}
MLT_PHYSICAL_ENCODING_NAMES = {
    0: "None",
    1: "SIMD-FastPFOR",
    2: "VarInt",
    3: "Reserved",
}

# Common classification fields found in OpenMapTiles/OSM, Natural Earth,
# national datasets, and generic GIS exports. The first suitable field wins.
SEMANTIC_KEY_PRIORITY = (
    "class",
    "subclass",
    "type",
    "kind",
    "kind_detail",
    "category",
    "fclass",
    "featurecla",
    "featureclass",
    "object_type",
    "objecttype",
    "objektart",
    "objektart_txt",
    "theme",
    "subtype",
    "landuse",
    "natural",
    "waterway",
    "highway",
    "railway",
    "building",
    "amenity",
    "place",
    "boundary",
    "wetland",
    "surface",
    "code",
)
NON_SEMANTIC_KEYS = {
    "name",
    "name_en",
    "name:en",
    "id",
    "fid",
    "gid",
    "osm_id",
    "osm_way_id",
    "ref",
    "uuid",
    "url",
    "website",
    "description",
    "wikidata",
    "wikipedia",
    "source",
}
MAX_TRACKED_DISTINCT_VALUES = 512
MAX_SAMPLE_VALUES = 12
BATCH_SIZE = 5000


@dataclass(frozen=True)
class PMTilesHeader:
    version: int
    root_offset: int
    root_length: int
    metadata_offset: int
    metadata_length: int
    leaf_directory_offset: int
    leaf_directory_length: int
    tile_data_offset: int
    tile_data_length: int
    addressed_tiles_count: int
    tile_entries_count: int
    tile_contents_count: int
    clustered: bool
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    center_zoom: int
    center_lon: float
    center_lat: float

    @property
    def format_name(self) -> str:
        return TILE_TYPE_NAMES.get(self.tile_type, f"TYPE_{self.tile_type}")

    @property
    def tile_compression_name(self) -> str:
        return COMPRESSION_NAMES.get(self.tile_compression, f"COMPRESSION_{self.tile_compression}")

    @property
    def internal_compression_name(self) -> str:
        return COMPRESSION_NAMES.get(self.internal_compression, f"COMPRESSION_{self.internal_compression}")


@dataclass(frozen=True)
class DirectoryEntry:
    tile_id: int
    offset: int
    length: int
    run_length: int


@dataclass(frozen=True)
class ArchiveInfo:
    path: Path
    header: PMTilesHeader
    metadata: dict

    @property
    def format_name(self) -> str:
        return self.header.format_name


@dataclass(frozen=True)
class ArchivePair:
    name: str
    mvt_path: Path
    mlt_path: Path


@dataclass
class BuildReport:
    db_path: Path
    input_dir: Path
    maps: int = 0
    archives: int = 0
    tiles: int = 0
    feature_instances: int = 0
    errors: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "db_path": str(self.db_path),
            "input_dir": str(self.input_dir),
            "maps": self.maps,
            "archives": self.archives,
            "tiles": self.tiles,
            "feature_instances": self.feature_instances,
            "errors": self.errors,
            "warnings": list(self.warnings),
        }


@dataclass
class PropertyTracker:
    occurrences: int = 0
    first_zoom: int | None = None
    last_zoom: int | None = None
    value_types: Counter[str] = field(default_factory=Counter)
    values: Counter[str] = field(default_factory=Counter)
    detail: Counter[tuple[int, str, str]] = field(default_factory=Counter)
    samples: list[str] = field(default_factory=list)
    high_cardinality: bool = False
    distinct_values_seen: int = 0

    def observe(self, value: object, zoom: int, geometry_type: str) -> None:
        self.occurrences += 1
        self.first_zoom = zoom if self.first_zoom is None else min(self.first_zoom, zoom)
        self.last_zoom = zoom if self.last_zoom is None else max(self.last_zoom, zoom)
        value_type = _value_type(value)
        self.value_types[value_type] += 1
        value_text = _value_to_text(value)
        if value_text not in self.samples and len(self.samples) < MAX_SAMPLE_VALUES:
            self.samples.append(value_text)

        if self.high_cardinality:
            return

        if value_text not in self.values and len(self.values) >= MAX_TRACKED_DISTINCT_VALUES:
            self.high_cardinality = True
            self.distinct_values_seen = MAX_TRACKED_DISTINCT_VALUES + 1
            self.values.clear()
            self.detail.clear()
            return

        self.values[value_text] += 1
        self.detail[(zoom, geometry_type, value_text)] += 1
        self.distinct_values_seen = len(self.values)


@dataclass
class LayerTracker:
    feature_instances: int = 0
    first_zoom: int | None = None
    last_zoom: int | None = None
    min_extent: int | None = None
    max_extent: int | None = None
    versions: set[int] = field(default_factory=set)
    geom_counts: Counter[str] = field(default_factory=Counter)
    zoom_geom_counts: Counter[tuple[int, str]] = field(default_factory=Counter)
    properties: dict[str, PropertyTracker] = field(default_factory=dict)

    def observe_layer(self, zoom: int, extent: int, version: int) -> None:
        self.first_zoom = zoom if self.first_zoom is None else min(self.first_zoom, zoom)
        self.last_zoom = zoom if self.last_zoom is None else max(self.last_zoom, zoom)
        self.min_extent = extent if self.min_extent is None else min(self.min_extent, extent)
        self.max_extent = extent if self.max_extent is None else max(self.max_extent, extent)
        self.versions.add(version)


@dataclass(frozen=True)
class FeatureObservation:
    geometry_type: str
    vertex_count: int
    geometry_command_ints: int
    geometry_command_count: int
    tag_pairs: int
    properties: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class LayerTileSummary:
    name: str
    extent: int
    version: int
    raw_layer_bytes: int
    isolated_gzip_layer_bytes: int
    key_count: int
    value_count: int
    key_utf8_bytes: int
    value_proto_bytes: int
    features: tuple[FeatureObservation, ...]


@dataclass(frozen=True)
class MVTTileSummary:
    layers: tuple[LayerTileSummary, ...]

    @property
    def total_features(self) -> int:
        return sum(len(layer.features) for layer in self.layers)

    @property
    def total_vertices(self) -> int:
        return sum(feature.vertex_count for layer in self.layers for feature in layer.features)

    @property
    def total_geometry_command_ints(self) -> int:
        return sum(feature.geometry_command_ints for layer in self.layers for feature in layer.features)

    @property
    def total_geometry_command_count(self) -> int:
        return sum(feature.geometry_command_count for layer in self.layers for feature in layer.features)

    @property
    def total_tag_pairs(self) -> int:
        return sum(feature.tag_pairs for layer in self.layers for feature in layer.features)

    @property
    def total_key_count(self) -> int:
        return sum(layer.key_count for layer in self.layers)

    @property
    def total_value_count(self) -> int:
        return sum(layer.value_count for layer in self.layers)


@dataclass(frozen=True)
class MLTColumnMeta:
    type_code: int
    type_name: str
    name: str
    nullable: bool
    children: tuple["MLTColumnMeta", ...] = ()


@dataclass(frozen=True)
class MLTStreamObservation:
    column_index: int
    column_name: str
    column_type: str
    stream_index: int
    stream_type_code: int
    stream_category: str
    stream_subtype: str
    stream_role: str
    encoding_code: int
    logical_encoding: str
    physical_encoding: str
    num_values: int
    payload_bytes: int
    header_bytes: int
    total_bytes: int
    runs: int | None = None
    num_rle_values: int | None = None
    morton_bits: int | None = None
    morton_shift: int | None = None


@dataclass(frozen=True)
class MLTLayerObservation:
    layer_index: int
    name: str
    tag: int
    extent: int | None
    column_count: int | None
    feature_count: int | None
    raw_frame_bytes: int
    isolated_gzip_frame_bytes: int
    metadata_bytes: int | None
    data_bytes: int | None
    streams: tuple[MLTStreamObservation, ...]
    parse_error: str | None = None


@dataclass(frozen=True)
class MLTTileObservation:
    layers: tuple[MLTLayerObservation, ...]

def _project_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    for base in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for candidate in (base, *base.parents):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def find_project_root() -> Path:
    for candidate in _project_root_candidates():
        if (candidate / "app" / "data" / "output").exists():
            return candidate
    for candidate in _project_root_candidates():
        if (candidate / "app" / "data").exists():
            return candidate
    for candidate in _project_root_candidates():
        if (candidate / "app").exists() and (candidate / "data").exists():
            return candidate
    return Path(__file__).resolve().parent


def get_default_paths() -> tuple[Path, Path]:
    root = find_project_root()
    return root / "app" / "data" / "output", root / "docs" / "data" / "tile_stats"


def read_pmtiles_header(path: str | Path) -> PMTilesHeader:
    path = Path(path)
    with path.open("rb") as handle:
        data = handle.read(PMTILES_HEADER_SIZE)
    if len(data) != PMTILES_HEADER_SIZE:
        raise ValueError(f"{path}: PMTiles header is shorter than {PMTILES_HEADER_SIZE} bytes")
    if data[:7] != PMTILES_MAGIC:
        raise ValueError(f"{path}: not a PMTiles archive")
    version = data[7]
    if version != PMTILES_VERSION:
        raise ValueError(f"{path}: unsupported PMTiles version {version}; expected version 3")

    u64 = lambda offset: struct.unpack_from("<Q", data, offset)[0]
    i32 = lambda offset: struct.unpack_from("<i", data, offset)[0]
    return PMTilesHeader(
        version=version,
        root_offset=u64(8),
        root_length=u64(16),
        metadata_offset=u64(24),
        metadata_length=u64(32),
        leaf_directory_offset=u64(40),
        leaf_directory_length=u64(48),
        tile_data_offset=u64(56),
        tile_data_length=u64(64),
        addressed_tiles_count=u64(72),
        tile_entries_count=u64(80),
        tile_contents_count=u64(88),
        clustered=bool(data[96]),
        internal_compression=data[97],
        tile_compression=data[98],
        tile_type=data[99],
        min_zoom=data[100],
        max_zoom=data[101],
        min_lon=i32(102) / 10_000_000.0,
        min_lat=i32(106) / 10_000_000.0,
        max_lon=i32(110) / 10_000_000.0,
        max_lat=i32(114) / 10_000_000.0,
        center_zoom=data[118],
        center_lon=i32(119) / 10_000_000.0,
        center_lat=i32(123) / 10_000_000.0,
    )


def _decompress(data: bytes, compression: int, what: str) -> bytes:
    if compression in {0, 1}:
        return data
    if compression == 2:
        return gzip.decompress(data)
    if compression == 3:
        try:
            import brotli
        except ImportError as exc:
            raise RuntimeError(
                f"Brotli is required to decompress {what}. Install it with: uv add brotli"
            ) from exc
        return brotli.decompress(data)
    if compression == 4:
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise RuntimeError(
                f"zstandard is required to decompress {what}. Install it with: uv add zstandard"
            ) from exc
        return zstd.ZstdDecompressor().decompress(data)
    raise ValueError(f"Unsupported/unknown PMTiles compression code {compression} for {what}")


def read_pmtiles_metadata(path: str | Path, header: PMTilesHeader | None = None) -> dict:
    path = Path(path)
    header = header or read_pmtiles_header(path)
    if header.metadata_length == 0:
        return {}
    with path.open("rb") as handle:
        handle.seek(header.metadata_offset)
        data = handle.read(header.metadata_length)
    data = _decompress(data, header.internal_compression, f"metadata in {path.name}")
    if not data:
        return {}
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{path}: invalid PMTiles JSON metadata") from exc
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def inspect_archive(path: str | Path) -> ArchiveInfo:
    path = Path(path).resolve()
    header = read_pmtiles_header(path)
    metadata = read_pmtiles_metadata(path, header)
    return ArchiveInfo(path=path, header=header, metadata=metadata)


def _canonical_map_name(path: Path) -> str:
    stem = path.name[:-8] if path.name.lower().endswith(".pmtiles") else path.stem
    stem = re.sub(r"(?i)([._-])(mvt|mlt)$", "", stem)
    stem = re.sub(r"(?i)^(mvt|mlt)([._-])", "", stem)
    return stem


def _is_transient_pmtiles(path: Path) -> bool:
    """Return True for converter scratch/intermediate PMTiles files.

    The conversion pipeline may leave files such as
    ``<dataset>_standard_buildings.group.tmp.pmtiles`` while assembling the
    final archive.  They are valid MVT PMTiles, but they are *not* study
    outputs and therefore must never participate in MVT/MLT pair discovery.

    Keep this deliberately narrow: incomplete *final* outputs should still be
    reported as errors rather than silently ignored.
    """
    name = path.name.lower()
    return name.endswith(".tmp.pmtiles") or name.endswith(".partial.pmtiles")


def discover_pairs(input_dir: str | Path | None = None) -> list[ArchivePair]:
    default_input, _ = get_default_paths()
    input_dir = Path(input_dir or default_input).resolve()
    if not input_dir.exists():
        return []

    grouped: dict[str, dict[str, Path]] = {}
    unsupported: list[str] = []
    for path in sorted(input_dir.rglob("*.pmtiles")):
        if _is_transient_pmtiles(path):
            continue
        header = read_pmtiles_header(path)
        format_name = header.format_name
        if format_name not in {FORMAT_MVT, FORMAT_MLT}:
            unsupported.append(f"{path.name} ({format_name})")
            continue
        name = _canonical_map_name(path)
        slot = grouped.setdefault(name, {})
        if format_name in slot:
            raise ValueError(
                f"More than one {format_name} archive maps to logical name '{name}': "
                f"{slot[format_name]} and {path}"
            )
        slot[format_name] = path.resolve()

    incomplete = {
        name: formats
        for name, formats in grouped.items()
        if FORMAT_MVT not in formats or FORMAT_MLT not in formats
    }
    if incomplete:
        details = "; ".join(
            f"{name}: has {', '.join(sorted(formats))}, missing "
            f"{FORMAT_MLT if FORMAT_MVT in formats else FORMAT_MVT}"
            for name, formats in sorted(incomplete.items())
        )
        raise ValueError(f"Incomplete MVT/MLT pairs in {input_dir}: {details}")

    pairs = [
        ArchivePair(name=name, mvt_path=formats[FORMAT_MVT], mlt_path=formats[FORMAT_MLT])
        for name, formats in sorted(grouped.items())
    ]
    if not pairs and unsupported:
        raise ValueError(
            "PMTiles archives were found, but none are MVT/MLT: " + ", ".join(unsupported)
        )
    return pairs


def _read_varint(stream: io.BytesIO) -> int:
    shift = 0
    result = 0
    while True:
        raw = stream.read(1)
        if not raw:
            raise EOFError("Unexpected end of PMTiles directory varint stream")
        value = raw[0]
        result |= (value & 0x7F) << shift
        if not (value & 0x80):
            return result
        shift += 7
        if shift > 70:
            raise ValueError("Invalid PMTiles varint")


def _deserialize_directory(data: bytes, compression: int) -> list[DirectoryEntry]:
    data = _decompress(data, compression, "PMTiles directory")
    stream = io.BytesIO(data)
    count = _read_varint(stream)
    entries = [DirectoryEntry(0, 0, 0, 0) for _ in range(count)]

    tile_ids: list[int] = []
    last_id = 0
    for _ in range(count):
        last_id += _read_varint(stream)
        tile_ids.append(last_id)

    run_lengths = [_read_varint(stream) for _ in range(count)]
    lengths = [_read_varint(stream) for _ in range(count)]
    offsets: list[int] = []
    for index in range(count):
        encoded = _read_varint(stream)
        if index > 0 and encoded == 0:
            offsets.append(offsets[index - 1] + lengths[index - 1])
        else:
            offsets.append(encoded - 1)

    return [
        DirectoryEntry(tile_ids[index], offsets[index], lengths[index], run_lengths[index])
        for index in range(count)
    ]


def _read_section(handle, offset: int, length: int) -> bytes:
    handle.seek(offset)
    data = handle.read(length)
    if len(data) != length:
        raise EOFError(f"Expected {length} bytes at offset {offset}, got {len(data)}")
    return data


def _iter_tile_runs_from_handle(handle, header: PMTilesHeader) -> Iterator[DirectoryEntry]:
    def walk(offset: int, length: int) -> Iterator[DirectoryEntry]:
        data = _read_section(handle, offset, length)
        entries = _deserialize_directory(data, header.internal_compression)
        for entry in entries:
            if entry.run_length > 0:
                yield entry
            else:
                leaf_offset = header.leaf_directory_offset + entry.offset
                yield from walk(leaf_offset, entry.length)

    yield from walk(header.root_offset, header.root_length)


def iter_tile_runs(path: str | Path, header: PMTilesHeader | None = None) -> Iterator[DirectoryEntry]:
    path = Path(path)
    header = header or read_pmtiles_header(path)
    with path.open("rb") as handle:
        yield from _iter_tile_runs_from_handle(handle, header)


def _rotate(n: int, x: int, y: int, rx: int, ry: int) -> tuple[int, int]:
    if ry == 0:
        if rx != 0:
            x = n - 1 - x
            y = n - 1 - y
        x, y = y, x
    return x, y


def tileid_to_zxy(tile_id: int) -> tuple[int, int, int]:
    z = ((3 * tile_id + 1).bit_length() - 1) // 2
    if z >= 32:
        raise OverflowError("Tile zoom exceeds PMTiles 64-bit limit")
    acc = ((1 << (z * 2)) - 1) // 3
    pos = tile_id - acc
    x = 0
    y = 0
    s = 1
    n = 1 << z
    while s < n:
        rx = (pos // 2) & s
        ry = (pos ^ rx) & s
        x, y = _rotate(s, x, y, rx, ry)
        x += rx
        y += ry
        pos >>= 1
        s <<= 1
    return z, x, y


@lru_cache(maxsize=1)
def _load_vector_tile_pb2():
    try:
        from mapbox_vector_tile.Mapbox import vector_tile_pb2
    except ImportError as exc:
        raise RuntimeError(
            "MVT semantic analysis requires mapbox-vector-tile. "
            "Install it with: uv add mapbox-vector-tile"
        ) from exc
    return vector_tile_pb2


def _protobuf_value(value_message) -> object:
    fields = (
        "string_value",
        "float_value",
        "double_value",
        "int_value",
        "uint_value",
        "sint_value",
        "bool_value",
    )
    for field_name in fields:
        try:
            if value_message.HasField(field_name):
                return getattr(value_message, field_name)
        except ValueError:
            pass
    return None



def _varint_wire_size(value: int) -> int:
    value = max(0, int(value))
    size = 1
    while value >= 0x80:
        value >>= 7
        size += 1
    return size


def _gzip_size(payload: bytes) -> int:
    # Fixed mtime makes the synthetic gzip size deterministic across runs.
    return len(gzip.compress(payload, compresslevel=6, mtime=0))


def _mvt_geometry_metrics(geometry: Sequence[int]) -> tuple[int, int]:
    """Return (vertex_count, command_header_count) from an MVT command stream."""
    position = 0
    vertices = 0
    commands = 0
    length = len(geometry)
    while position < length:
        command_integer = int(geometry[position])
        position += 1
        command_id = command_integer & 0x7
        count = command_integer >> 3
        commands += 1
        if count <= 0:
            break
        if command_id in {1, 2}:  # MoveTo / LineTo: each vertex has x/y parameters.
            vertices += count
            position += 2 * count
        elif command_id == 7:  # ClosePath has no parameters.
            continue
        else:
            # Unknown command: retain the already observed command count and stop;
            # this prevents a malformed feature from desynchronizing the parser.
            break
        if position > length:
            break
    return vertices, commands


def _read_mlt_varint(data: bytes, position: int, end: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while position < end:
        value = data[position]
        position += 1
        result |= (value & 0x7F) << shift
        if not (value & 0x80):
            return result, position
        shift += 7
        if shift > 70:
            raise ValueError("MLT varint is too long")
    raise EOFError("Unexpected end of MLT varint")


def _read_mlt_string(data: bytes, position: int, end: int) -> tuple[str, int]:
    length, position = _read_mlt_varint(data, position, end)
    next_position = position + length
    if next_position > end:
        raise EOFError("MLT string extends beyond frame")
    return data[position:next_position].decode("utf-8", errors="replace"), next_position


def _mlt_stream_names(stream_type: int) -> tuple[str, str, str]:
    category_code = (stream_type >> 4) & 0x0F
    subtype_code = stream_type & 0x0F
    category = MLT_STREAM_CATEGORY_NAMES.get(category_code, f"Category{category_code}")
    subtype = MLT_STREAM_SUBTYPE_NAMES.get(category_code, {}).get(subtype_code, f"Subtype{subtype_code}")
    role = category if category == "Present" else f"{category}/{subtype}"
    return category, subtype, role


def _mlt_hex_preview(
    data: bytes,
    position: int,
    end: int,
    limit: int = 64,
) -> str:
    """Return a compact hex preview without reading beyond the current MLT frame."""
    start = max(0, min(int(position), int(end)))
    stop = min(int(end), start + max(0, int(limit)))

    preview = data[start:stop].hex(" ")
    if stop < end:
        preview += " ..."

    return preview


def _parse_mlt_stream(
    data: bytes,
    position: int,
    end: int,
    *,
    layer_name: str,
    body_start: int,
    column_index: int,
    column_name: str,
    column_type: str,
    stream_index: int,
) -> tuple[MLTStreamObservation, int]:
    """Parse one MLT v1 stream with strict structural diagnostics.

    Important MLT v1 detail:
    boolean RLE streams do NOT store `runs` and `num_rle_values`
    explicitly in the stream header. This applies both to Present streams
    and to Data streams belonging to Bool / OptBool columns.

    For boolean RLE:
        runs = ceil(num_values / 8)
        num_rle_values = byte_length

    This mirrors the reference mlt-core v1 parser.
    """
    start = position

    try:
        if position + 2 > end:
            raise EOFError("MLT stream header is truncated")

        stream_type = data[position]
        encoding = data[position + 1]
        position += 2

        category_code = (stream_type >> 4) & 0x0F
        subtype_code = stream_type & 0x0F

        if category_code not in MLT_STREAM_CATEGORY_NAMES:
            raise ValueError(
                f"invalid MLT stream category {category_code} "
                f"(stream_type=0x{stream_type:02x})"
            )

        valid_subtypes = MLT_STREAM_SUBTYPE_NAMES.get(
            category_code,
            {},
        )

        if subtype_code not in valid_subtypes:
            raise ValueError(
                f"invalid MLT stream subtype {subtype_code} "
                f"for category {category_code} "
                f"(stream_type=0x{stream_type:02x})"
            )

        category = MLT_STREAM_CATEGORY_NAMES[category_code]
        subtype = valid_subtypes[subtype_code]

        role = (
            category
            if category == "Present"
            else f"{category}/{subtype}"
        )

        logical1 = (encoding >> 5) & 0x07
        logical2 = (encoding >> 2) & 0x07
        physical = encoding & 0x03

        logical_key = (logical1, logical2)

        if logical_key not in MLT_LOGICAL_ENCODING_NAMES:
            raise ValueError(
                f"unknown MLT logical encoding "
                f"L{logical1}:{logical2} "
                f"(encoding=0x{encoding:02x}, stream={role})"
            )

        if physical not in {0, 1, 2}:
            raise ValueError(
                f"reserved/invalid MLT physical encoding {physical} "
                f"(encoding=0x{encoding:02x}, stream={role})"
            )

        logical_name = MLT_LOGICAL_ENCODING_NAMES[logical_key]
        physical_name = MLT_PHYSICAL_ENCODING_NAMES[physical]

        num_values, position = _read_mlt_varint(
            data,
            position,
            end,
        )

        byte_length, position = _read_mlt_varint(
            data,
            position,
            end,
        )

        # In MLT v1 both of these are boolean streams:
        #
        #   1. every Present stream;
        #   2. the Data stream of Bool / OptBool columns.
        #
        # Boolean RLE does NOT carry explicit `runs` and
        # `num_rle_values` varints in the wire header.
        is_boolean = (
            category == "Present"
            or column_type in {"Bool", "OptBool"}
        )

        runs = None
        num_rle_values = None

        is_rle = logical_key in {
            (3, 0),  # RLE
            (1, 3),  # DeltaRLE
        }

        if is_rle:
            if is_boolean:
                # Reference MLT v1 behaviour:
                #
                # encoded boolean input is first bit-packed into
                # ceil(num_values / 8) bytes and then byte-RLE encoded.
                #
                # The two RLE metadata values are implicit.
                runs = (num_values + 7) // 8
                num_rle_values = byte_length

            else:
                runs, position = _read_mlt_varint(
                    data,
                    position,
                    end,
                )

                num_rle_values, position = _read_mlt_varint(
                    data,
                    position,
                    end,
                )

        morton_bits = None
        morton_shift = None

        if (
            subtype == "Morton"
            or logical_key == (4, 1)
        ):
            morton_bits, position = _read_mlt_varint(
                data,
                position,
                end,
            )

            morton_shift, position = _read_mlt_varint(
                data,
                position,
                end,
            )

        payload_start = position
        payload_end = payload_start + byte_length

        if payload_end > end:
            raise EOFError(
                f"MLT stream {role} payload "
                f"({byte_length} B) extends beyond layer frame; "
                f"payload_start={payload_start - body_start}, "
                f"frame_remaining={end - payload_start}"
            )

        observation = MLTStreamObservation(
            column_index=column_index,
            column_name=column_name,
            column_type=column_type,
            stream_index=stream_index,
            stream_type_code=stream_type,
            stream_category=category,
            stream_subtype=subtype,
            stream_role=role,
            encoding_code=encoding,
            logical_encoding=logical_name,
            physical_encoding=physical_name,
            num_values=num_values,
            payload_bytes=byte_length,
            header_bytes=payload_start - start,
            total_bytes=payload_end - start,
            runs=runs,
            num_rle_values=num_rle_values,
            morton_bits=morton_bits,
            morton_shift=morton_shift,
        )

        return observation, payload_end

    except Exception as exc:
        preview = _mlt_hex_preview(
            data,
            start,
            end,
        )

        context = (
            f"layer={layer_name!r}, "
            f"column_index={column_index}, "
            f"column_name={column_name!r}, "
            f"column_type={column_type!r}, "
            f"stream_index={stream_index}, "
            f"stream_offset={start - body_start}, "
            f"remaining_in_layer={end - start}, "
            f"next_bytes={preview}"
        )

        raise type(exc)(
            f"{exc}; {context}"
        ) from exc


def _parse_mlt_column_meta(data: bytes, position: int, end: int) -> tuple[MLTColumnMeta, int]:
    if position >= end:
        raise EOFError("MLT column metadata is truncated")
    type_code = data[position]
    position += 1
    if type_code not in MLT_COLUMN_TYPES:
        raise ValueError(f"Unsupported MLT v1 column type 0x{type_code:02x}")
    type_name = MLT_COLUMN_TYPES[type_code]
    base_type = type_code & ~1
    nullable = bool(type_code & 1)
    if base_type in {0, 2, 4}:  # ids and geometry have implicit names
        name = "id" if base_type in {0, 2} else "geometry"
    else:
        name, position = _read_mlt_string(data, position, end)

    children: list[MLTColumnMeta] = []
    if type_code == 30:
        child_count, position = _read_mlt_varint(data, position, end)
        for _ in range(child_count):
            child, position = _parse_mlt_column_meta(data, position, end)
            children.append(child)

    return MLTColumnMeta(type_code, type_name, name, nullable, tuple(children)), position


def _parse_mlt_layer_body(
    data: bytes,
    body_start: int,
    body_end: int,
    *,
    layer_index: int,
    tag: int,
    frame_start: int,
    frame_end: int,
) -> MLTLayerObservation:
    """Parse one stable-v1 MLT layer with detailed per-column diagnostics."""
    position = body_start

    name, position = _read_mlt_string(
        data,
        position,
        body_end,
    )
    extent, position = _read_mlt_varint(
        data,
        position,
        body_end,
    )
    column_count, position = _read_mlt_varint(
        data,
        position,
        body_end,
    )

    columns: list[MLTColumnMeta] = []

    for _ in range(column_count):
        column, position = _parse_mlt_column_meta(
            data,
            position,
            body_end,
        )
        columns.append(column)

    data_start = position
    streams: list[MLTStreamObservation] = []
    feature_count = None

    column_trace: list[str] = []

    for column_index, column in enumerate(columns):
        column_start = position
        base_type = column.type_code & ~1
        stream_index = 0

        previous_column = (
            columns[column_index - 1]
            if column_index > 0
            else None
        )

        def parse_one(
            column_name: str,
            column_type: str,
        ) -> MLTStreamObservation:
            nonlocal position, stream_index

            stream, position = _parse_mlt_stream(
                data,
                position,
                body_end,
                layer_name=name,
                body_start=body_start,
                column_index=column_index,
                column_name=column_name,
                column_type=column_type,
                stream_index=stream_index,
            )

            stream_index += 1
            streams.append(stream)

            return stream

        try:
            if base_type == 4:
                # Geometry
                stream_count, position = _read_mlt_varint(
                    data,
                    position,
                    body_end,
                )

                for _ in range(stream_count):
                    stream = parse_one(
                        column.name,
                        column.type_name,
                    )

                    if feature_count is None:
                        feature_count = stream.num_values

            elif base_type == 28:
                # String / OptString
                stream_count, position = _read_mlt_varint(
                    data,
                    position,
                    body_end,
                )

                for _ in range(stream_count):
                    parse_one(
                        column.name,
                        column.type_name,
                    )

            elif column.type_code == 30:
                # Shared dictionary
                declared_stream_count, position = _read_mlt_varint(
                    data,
                    position,
                    body_end,
                )

                parsed_stream_count = 0
                child_diagnostics: list[str] = []

                if position >= body_end:
                    raise EOFError(
                        "SharedDict ends immediately after declared stream count"
                    )

                probe_type = data[position]
                _, _, probe_role = _mlt_stream_names(probe_type)

                if probe_role == "Length/Symbol":
                    dictionary_streams = 4

                elif probe_role == "Length/Dictionary":
                    dictionary_streams = 2

                else:
                    raise ValueError(
                        "SharedDict dictionary does not start with "
                        "Length/Symbol or Length/Dictionary; "
                        f"probe_stream_type=0x{probe_type:02x}, "
                        f"probe_role={probe_role}"
                    )

                dictionary_roles: list[str] = []

                for _ in range(dictionary_streams):
                    stream = parse_one(
                        column.name,
                        column.type_name,
                    )

                    dictionary_roles.append(
                        stream.stream_role
                    )
                    parsed_stream_count += 1

                for child_index, child in enumerate(column.children):
                    child_count_offset = position

                    child_stream_count, position = _read_mlt_varint(
                        data,
                        position,
                        body_end,
                    )

                    child_name = f"{column.name}{child.name}"
                    child_start = position
                    child_roles: list[str] = []

                    for _ in range(child_stream_count):
                        stream = parse_one(
                            child_name,
                            child.type_name,
                        )

                        child_roles.append(
                            stream.stream_role
                        )
                        parsed_stream_count += 1

                    child_diagnostics.append(
                        f"child[{child_index}]={child_name!r}/"
                        f"{child.type_name},"
                        f"nullable={child.nullable},"
                        f"declared={child_stream_count},"
                        f"count_offset={child_count_offset - body_start},"
                        f"bytes={position - child_start},"
                        f"roles={child_roles}"
                    )

                if declared_stream_count not in {
                    parsed_stream_count,
                    parsed_stream_count + 1,
                }:
                    raise ValueError(
                        "SharedDict stream-count mismatch: "
                        f"declared={declared_stream_count}, "
                        f"parsed={parsed_stream_count}, "
                        f"dictionary_streams={dictionary_streams}, "
                        f"dictionary_roles={dictionary_roles}, "
                        f"children=[{'; '.join(child_diagnostics)}]"
                    )

            else:
                # Scalar / Id
                if column.nullable:
                    parse_one(
                        column.name,
                        column.type_name,
                    )

                parse_one(
                    column.name,
                    column.type_name,
                )

            column_end = position

            column_trace.append(
                f"[{column_index}] "
                f"{column.name!r}:{column.type_name} "
                f"nullable={column.nullable} "
                f"start={column_start - body_start} "
                f"end={column_end - body_start} "
                f"bytes={column_end - column_start} "
                f"streams={stream_index}"
            )

        except Exception as exc:
            preview = _mlt_hex_preview(
                data,
                position,
                body_end,
            )

            current_metadata = (
                f"[{column_index}] "
                f"{column.name!r}:{column.type_name}, "
                f"nullable={column.nullable}"
            )

            if previous_column is None:
                previous_metadata = "<none>"
            else:
                previous_metadata = (
                    f"[{column_index - 1}] "
                    f"{previous_column.name!r}:"
                    f"{previous_column.type_name}, "
                    f"nullable={previous_column.nullable}"
                )

            metadata_order = " | ".join(
                f"[{idx}] {col.name!r}:{col.type_name}"
                f"{'?' if col.nullable else ''}"
                for idx, col in enumerate(columns)
            )

            completed_trace = " || ".join(column_trace)

            context = (
                f"current_column={current_metadata}; "
                f"previous_column={previous_metadata}; "
                f"column_start_offset={column_start - body_start}; "
                f"current_offset={position - body_start}; "
                f"remaining_in_layer={body_end - position}; "
                f"next_bytes={preview}; "
                f"completed_columns={completed_trace}; "
                f"metadata_order={metadata_order}"
            )

            raise type(exc)(
                f"{exc}; {context}"
            ) from exc

    if position != body_end:
        remaining = body_end - position

        preview = _mlt_hex_preview(
            data,
            position,
            body_end,
        )

        completed_trace = " || ".join(column_trace)

        metadata_order = " | ".join(
            f"[{idx}] {col.name!r}:{col.type_name}"
            f"{'?' if col.nullable else ''}"
            for idx, col in enumerate(columns)
        )

        raise ValueError(
            f"MLT v1 layer {name!r} "
            f"parsed to offset {position - body_start}, "
            f"but frame body is {body_end - body_start} bytes; "
            f"remaining_bytes={remaining}; "
            f"next_bytes={preview}; "
            f"completed_columns={completed_trace}; "
            f"metadata_order={metadata_order}"
        )

    frame = data[frame_start:frame_end]

    return MLTLayerObservation(
        layer_index=layer_index,
        name=name,
        tag=tag,
        extent=extent,
        column_count=column_count,
        feature_count=feature_count,
        raw_frame_bytes=len(frame),
        isolated_gzip_frame_bytes=_gzip_size(frame),
        metadata_bytes=data_start - body_start,
        data_bytes=body_end - data_start,
        streams=tuple(streams),
        parse_error=None,
    )


def _parse_mlt_payload(
    payload: bytes,
) -> MLTTileObservation:
    """Parse an MLT tile while preserving the real layer name on parse failures."""
    layers: list[MLTLayerObservation] = []

    position = 0
    layer_index = 0

    while position < len(payload):
        frame_start = position

        size, after_size = _read_mlt_varint(
            payload,
            position,
            len(payload),
        )

        if size <= 0:
            raise ValueError(
                "MLT frame size must be positive"
            )

        frame_end = after_size + size

        if frame_end > len(payload):
            raise EOFError(
                "MLT frame extends beyond tile payload"
            )

        tag = payload[after_size]
        body_start = after_size + 1

        if tag == MLT_V1_TAG:
            try:
                fallback_name, _ = _read_mlt_string(
                    payload,
                    body_start,
                    frame_end,
                )
            except Exception:
                fallback_name = f"<unparsed:{layer_index}>"

            try:
                layer = _parse_mlt_layer_body(
                    payload,
                    body_start,
                    frame_end,
                    layer_index=layer_index,
                    tag=tag,
                    frame_start=frame_start,
                    frame_end=frame_end,
                )

            except Exception as exc:
                frame = payload[frame_start:frame_end]

                layer = MLTLayerObservation(
                    layer_index=layer_index,
                    name=fallback_name,
                    tag=tag,
                    extent=None,
                    column_count=None,
                    feature_count=None,
                    raw_frame_bytes=len(frame),
                    isolated_gzip_frame_bytes=_gzip_size(frame),
                    metadata_bytes=None,
                    data_bytes=None,
                    streams=(),
                    parse_error=f"{type(exc).__name__}: {exc}",
                )

        else:
            frame = payload[frame_start:frame_end]

            layer = MLTLayerObservation(
                layer_index=layer_index,
                name=f"<tag-0x{tag:02x}:{layer_index}>",
                tag=tag,
                extent=None,
                column_count=None,
                feature_count=None,
                raw_frame_bytes=len(frame),
                isolated_gzip_frame_bytes=_gzip_size(frame),
                metadata_bytes=None,
                data_bytes=None,
                streams=(),
                parse_error=(
                    f"MLT frame tag 0x{tag:02x} is not v1; "
                    "byte-level stream inspection is currently "
                    "implemented for stable v1 frames only"
                ),
            )

        layers.append(layer)

        position = frame_end
        layer_index += 1

    return MLTTileObservation(
        tuple(layers)
    )


def _parse_mvt_payload(payload: bytes) -> MVTTileSummary:
    vector_tile_pb2 = _load_vector_tile_pb2()

    tile_class = getattr(vector_tile_pb2, "tile", None)
    if tile_class is None:
        tile_class = getattr(vector_tile_pb2, "Tile", None)

    if tile_class is None:
        available = sorted(
            name
            for name in dir(vector_tile_pb2)
            if not name.startswith("_")
        )
        raise RuntimeError(
            "Cannot find MVT protobuf tile message in "
            "mapbox_vector_tile.Mapbox.vector_tile_pb2. "
            f"Available symbols: {available}"
        )

    tile = tile_class()
    tile.ParseFromString(payload)

    layer_summaries: list[LayerTileSummary] = []

    for layer in tile.layers:
        keys = list(layer.keys)
        value_messages = list(layer.values)
        values = [_protobuf_value(value) for value in value_messages]
        feature_observations: list[FeatureObservation] = []

        for feature in layer.features:
            properties: list[tuple[str, object]] = []
            tags = list(feature.tags)

            for index in range(0, len(tags) - 1, 2):
                key_index = tags[index]
                value_index = tags[index + 1]
                if key_index < len(keys) and value_index < len(values):
                    properties.append((keys[key_index], values[value_index]))

            vertex_count, geometry_command_count = _mvt_geometry_metrics(feature.geometry)
            feature_observations.append(
                FeatureObservation(
                    geometry_type=GEOMETRY_NAMES.get(
                        int(feature.type),
                        f"GEOM_{int(feature.type)}",
                    ),
                    vertex_count=vertex_count,
                    geometry_command_ints=len(feature.geometry),
                    geometry_command_count=geometry_command_count,
                    tag_pairs=len(tags) // 2,
                    properties=tuple(properties),
                )
            )

        serialized_layer = layer.SerializeToString()
        # MVT Tile.layers is field #3, wire type 2. Include its one-byte field
        # tag and length varint so layer wire sizes add up to the tile payload.
        layer_wire = b"\x1a" + _encode_varint_for_size(len(serialized_layer)) + serialized_layer
        layer_summaries.append(
            LayerTileSummary(
                name=layer.name,
                extent=int(layer.extent),
                version=int(layer.version),
                raw_layer_bytes=len(layer_wire),
                isolated_gzip_layer_bytes=_gzip_size(layer_wire),
                key_count=len(keys),
                value_count=len(value_messages),
                key_utf8_bytes=sum(len(str(key).encode("utf-8")) for key in keys),
                value_proto_bytes=sum(len(value.SerializeToString()) for value in value_messages),
                features=tuple(feature_observations),
            )
        )

    return MVTTileSummary(layers=tuple(layer_summaries))


def _encode_varint_for_size(value: int) -> bytes:
    out = bytearray()
    value = int(value)
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _value_to_text(value: object) -> str:
    if value is None:
        return "<null>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)


def _apply_tile_summary(
    layer_trackers: dict[str, LayerTracker],
    summary: MVTTileSummary,
    zoom: int,
) -> None:
    for layer in summary.layers:
        tracker = layer_trackers.get(layer.name)
        if tracker is None:
            tracker = layer_trackers[layer.name] = LayerTracker()
        tracker.observe_layer(zoom, layer.extent, layer.version)
        for feature in layer.features:
            tracker.feature_instances += 1
            tracker.geom_counts[feature.geometry_type] += 1
            tracker.zoom_geom_counts[(zoom, feature.geometry_type)] += 1
            seen_keys: set[str] = set()
            for key, value in feature.properties:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                prop = tracker.properties.get(key)
                if prop is None:
                    prop = tracker.properties[key] = PropertyTracker()
                prop.observe(value, zoom, feature.geometry_type)


def _semantic_key_for_layer(tracker: LayerTracker) -> str | None:
    if not tracker.properties or tracker.feature_instances == 0:
        return None

    by_lower = {key.lower(): key for key in tracker.properties}
    for preferred in SEMANTIC_KEY_PRIORITY:
        actual = by_lower.get(preferred)
        if actual is None:
            continue
        prop = tracker.properties[actual]
        coverage = prop.occurrences / tracker.feature_instances
        if not prop.high_cardinality and prop.distinct_values_seen > 0 and coverage >= 0.05:
            return actual

    candidates: list[tuple[float, int, str]] = []
    for key, prop in tracker.properties.items():
        if key.lower() in NON_SEMANTIC_KEYS or prop.high_cardinality:
            continue
        distinct = prop.distinct_values_seen
        if not 2 <= distinct <= 64:
            continue
        coverage = prop.occurrences / tracker.feature_instances
        if coverage < 0.5:
            continue
        ratio = distinct / max(prop.occurrences, 1)
        if ratio > 0.2:
            continue
        string_share = prop.value_types.get("string", 0) / max(prop.occurrences, 1)
        score = coverage + string_share - ratio
        candidates.append((score, -distinct, key))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = NORMAL;
        PRAGMA temp_store = MEMORY;

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE maps (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            dataset_name TEXT NOT NULL,
            variant TEXT NOT NULL,
            density_factor INTEGER NOT NULL,
            semantics_source TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE archives (
            id INTEGER PRIMARY KEY,
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            format TEXT NOT NULL CHECK(format IN ('MVT', 'MLT')),
            path TEXT NOT NULL,
            file_bytes INTEGER NOT NULL,
            pmtiles_version INTEGER NOT NULL,
            tile_type_code INTEGER NOT NULL,
            tile_compression TEXT NOT NULL,
            internal_compression TEXT NOT NULL,
            min_zoom INTEGER NOT NULL,
            max_zoom INTEGER NOT NULL,
            min_lon REAL NOT NULL,
            min_lat REAL NOT NULL,
            max_lon REAL NOT NULL,
            max_lat REAL NOT NULL,
            center_zoom INTEGER NOT NULL,
            center_lon REAL NOT NULL,
            center_lat REAL NOT NULL,
            addressed_tiles_header INTEGER NOT NULL,
            tile_entries_header INTEGER NOT NULL,
            tile_contents_header INTEGER NOT NULL,
            root_directory_bytes INTEGER NOT NULL,
            metadata_bytes INTEGER NOT NULL,
            leaf_directories_bytes INTEGER NOT NULL,
            tile_data_bytes INTEGER NOT NULL,
            clustered INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            UNIQUE(map_id, format)
        );

        CREATE TABLE tiles (
            archive_id INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
            z INTEGER NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            stored_bytes INTEGER NOT NULL,
            raw_payload_bytes INTEGER,
            gzip_payload_bytes INTEGER,
            content_offset INTEGER NOT NULL,
            PRIMARY KEY (archive_id, z, x, y)
        ) WITHOUT ROWID;

        CREATE TABLE tile_content_stats (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            z INTEGER NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            feature_instances INTEGER NOT NULL,
            vertex_count INTEGER NOT NULL,
            geometry_command_ints INTEGER NOT NULL,
            geometry_command_count INTEGER NOT NULL,
            tag_pairs INTEGER NOT NULL,
            layer_count INTEGER NOT NULL,
            property_key_count INTEGER NOT NULL,
            property_value_count INTEGER NOT NULL,
            PRIMARY KEY (map_id, z, x, y)
        ) WITHOUT ROWID;

        CREATE TABLE tile_layers (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            z INTEGER NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            layer_name TEXT NOT NULL,
            extent INTEGER NOT NULL,
            mvt_version INTEGER NOT NULL,
            feature_instances INTEGER NOT NULL,
            vertex_count INTEGER NOT NULL,
            geometry_command_ints INTEGER NOT NULL,
            geometry_command_count INTEGER NOT NULL,
            tag_pairs INTEGER NOT NULL,
            mvt_raw_layer_bytes INTEGER NOT NULL,
            mvt_isolated_gzip_layer_bytes INTEGER NOT NULL,
            mvt_key_count INTEGER NOT NULL,
            mvt_value_count INTEGER NOT NULL,
            mvt_key_utf8_bytes INTEGER NOT NULL,
            mvt_value_proto_bytes INTEGER NOT NULL,
            PRIMARY KEY (map_id, z, x, y, layer_name)
        ) WITHOUT ROWID;

        CREATE TABLE tile_layer_stats (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            z INTEGER NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            layer_name TEXT NOT NULL,
            geometry_type TEXT NOT NULL,
            feature_instances INTEGER NOT NULL,
            vertex_count INTEGER NOT NULL,
            geometry_command_ints INTEGER NOT NULL,
            geometry_command_count INTEGER NOT NULL,
            tag_pairs INTEGER NOT NULL,
            PRIMARY KEY (map_id, z, x, y, layer_name, geometry_type)
        ) WITHOUT ROWID;

        CREATE TABLE mlt_layers (
            archive_id INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
            content_offset INTEGER NOT NULL,
            content_length INTEGER NOT NULL,
            layer_index INTEGER NOT NULL,
            layer_name TEXT NOT NULL,
            frame_tag INTEGER NOT NULL,
            extent INTEGER,
            column_count INTEGER,
            feature_count INTEGER,
            raw_frame_bytes INTEGER NOT NULL,
            isolated_gzip_frame_bytes INTEGER NOT NULL,
            metadata_bytes INTEGER,
            data_bytes INTEGER,
            stream_count INTEGER NOT NULL,
            stream_payload_bytes INTEGER NOT NULL,
            stream_overhead_bytes INTEGER NOT NULL,
            parse_error TEXT,
            PRIMARY KEY (archive_id, content_offset, content_length, layer_index)
        ) WITHOUT ROWID;

        CREATE TABLE mlt_streams (
            archive_id INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
            content_offset INTEGER NOT NULL,
            content_length INTEGER NOT NULL,
            layer_index INTEGER NOT NULL,
            layer_name TEXT NOT NULL,
            column_index INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            column_type TEXT NOT NULL,
            stream_index INTEGER NOT NULL,
            stream_type_code INTEGER NOT NULL,
            stream_category TEXT NOT NULL,
            stream_subtype TEXT NOT NULL,
            stream_role TEXT NOT NULL,
            encoding_code INTEGER NOT NULL,
            logical_encoding TEXT NOT NULL,
            physical_encoding TEXT NOT NULL,
            num_values INTEGER NOT NULL,
            payload_bytes INTEGER NOT NULL,
            header_bytes INTEGER NOT NULL,
            total_bytes INTEGER NOT NULL,
            runs INTEGER,
            num_rle_values INTEGER,
            morton_bits INTEGER,
            morton_shift INTEGER,
            PRIMARY KEY (
                archive_id, content_offset, content_length,
                layer_index, column_index, column_name, stream_index
            )
        ) WITHOUT ROWID;

        CREATE TABLE layers (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            layer_name TEXT NOT NULL,
            feature_instances INTEGER NOT NULL,
            min_zoom INTEGER,
            max_zoom INTEGER,
            min_extent INTEGER,
            max_extent INTEGER,
            mvt_versions TEXT NOT NULL,
            semantic_key TEXT,
            point_instances INTEGER NOT NULL,
            linestring_instances INTEGER NOT NULL,
            polygon_instances INTEGER NOT NULL,
            unknown_instances INTEGER NOT NULL,
            PRIMARY KEY (map_id, layer_name)
        ) WITHOUT ROWID;

        CREATE TABLE properties (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            layer_name TEXT NOT NULL,
            property_key TEXT NOT NULL,
            feature_occurrences INTEGER NOT NULL,
            value_types TEXT NOT NULL,
            distinct_values_capped INTEGER NOT NULL,
            high_cardinality INTEGER NOT NULL,
            sample_values_json TEXT NOT NULL,
            min_zoom INTEGER,
            max_zoom INTEGER,
            PRIMARY KEY (map_id, layer_name, property_key)
        ) WITHOUT ROWID;

        CREATE TABLE semantic_types (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            layer_name TEXT NOT NULL,
            semantic_key TEXT NOT NULL,
            semantic_value TEXT NOT NULL,
            geometry_type TEXT NOT NULL,
            zoom INTEGER NOT NULL,
            feature_instances INTEGER NOT NULL,
            PRIMARY KEY (map_id, layer_name, semantic_key, semantic_value, geometry_type, zoom)
        ) WITHOUT ROWID;

        CREATE TABLE property_values (
            map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
            layer_name TEXT NOT NULL,
            property_key TEXT NOT NULL,
            property_value TEXT NOT NULL,
            geometry_type TEXT NOT NULL,
            zoom INTEGER NOT NULL,
            feature_instances INTEGER NOT NULL,
            PRIMARY KEY (map_id, layer_name, property_key, property_value, geometry_type, zoom)
        ) WITHOUT ROWID;

        CREATE TABLE pair_validation (
            map_id INTEGER PRIMARY KEY REFERENCES maps(id) ON DELETE CASCADE,
            mvt_tile_count INTEGER NOT NULL,
            mlt_tile_count INTEGER NOT NULL,
            missing_in_mlt INTEGER NOT NULL,
            missing_in_mvt INTEGER NOT NULL,
            same_tile_coordinates INTEGER NOT NULL
        );

        CREATE TABLE analysis_errors (
            id INTEGER PRIMARY KEY,
            map_id INTEGER REFERENCES maps(id) ON DELETE CASCADE,
            archive_format TEXT,
            z INTEGER,
            x INTEGER,
            y INTEGER,
            message TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("created_at_utc", datetime.now(timezone.utc).isoformat()),
            (
                "counting_semantics",
                "feature instances in tiles; the same source feature may occur in multiple tiles and zooms",
            ),
            (
                "tile_size_semantics",
                "raw_payload_bytes is decompressed size; gzip_payload_bytes is deterministic gzip.compress(level=6, mtime=0) for BOTH formats; stored_bytes is original PMTiles storage",
            ),
            (
                "mlt_stream_semantics",
                "MLT v1 stream byte counts are exact pre-external-gzip wire bytes. External gzip spans the whole tile, so gzip savings cannot be uniquely assigned to individual streams.",
            ),
        ],
    )


def _create_indexes_and_views(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX idx_archives_map_format ON archives(map_id, format);
        CREATE INDEX idx_tiles_zxy ON tiles(z, x, y);
        CREATE INDEX idx_tiles_content ON tiles(archive_id, content_offset, stored_bytes);
        CREATE INDEX idx_content_map_zoom ON tile_content_stats(map_id, z);
        CREATE INDEX idx_tile_layers_map_zoom ON tile_layers(map_id, z, layer_name);
        CREATE INDEX idx_layer_map_zoom ON tile_layer_stats(map_id, z, layer_name);
        CREATE INDEX idx_mlt_layers_content ON mlt_layers(archive_id, content_offset, content_length);
        CREATE INDEX idx_mlt_streams_content ON mlt_streams(archive_id, content_offset, content_length);
        CREATE INDEX idx_mlt_streams_role ON mlt_streams(stream_role, logical_encoding, physical_encoding);
        CREATE INDEX idx_semantic_map_layer_zoom ON semantic_types(map_id, layer_name, zoom);
        CREATE INDEX idx_property_values_map_layer ON property_values(map_id, layer_name, property_key);

        CREATE VIEW v_tile_comparison AS
        SELECT
            m.name AS map_name,
            m.dataset_name,
            m.variant,
            m.density_factor,
            mt.z,
            mt.x,
            mt.y,
            COALESCE(c.feature_instances, 0) AS feature_instances,
            COALESCE(c.vertex_count, 0) AS vertex_count,
            COALESCE(c.geometry_command_ints, 0) AS geometry_command_ints,
            COALESCE(c.geometry_command_count, 0) AS geometry_command_count,
            COALESCE(c.tag_pairs, 0) AS tag_pairs,
            COALESCE(c.layer_count, 0) AS layer_count,
            COALESCE(c.property_key_count, 0) AS property_key_count,
            COALESCE(c.property_value_count, 0) AS property_value_count,

            mt.raw_payload_bytes AS mvt_raw_bytes,
            mt.gzip_payload_bytes AS mvt_gzip_bytes,
            mt.stored_bytes AS mvt_stored_bytes,
            lt.raw_payload_bytes AS mlt_raw_bytes,
            lt.gzip_payload_bytes AS mlt_gzip_bytes,
            lt.stored_bytes AS mlt_stored_bytes,

            -- Backward-compatible aliases: generated archives are normally gzip-compressed.
            mt.stored_bytes AS mvt_bytes,
            lt.stored_bytes AS mlt_bytes,
            mt.raw_payload_bytes AS mvt_raw_payload_bytes,
            lt.raw_payload_bytes AS mlt_raw_payload_bytes,

            CASE WHEN mt.raw_payload_bytes > 0 AND mt.gzip_payload_bytes IS NOT NULL
                THEN 1.0 - (1.0 * mt.gzip_payload_bytes / mt.raw_payload_bytes)
                ELSE NULL END AS mvt_gzip_saving_fraction,
            CASE WHEN mt.raw_payload_bytes > 0 AND lt.raw_payload_bytes IS NOT NULL
                THEN 1.0 - (1.0 * lt.raw_payload_bytes / mt.raw_payload_bytes)
                ELSE NULL END AS mlt_raw_saving_fraction,
            CASE WHEN mt.gzip_payload_bytes > 0 AND lt.gzip_payload_bytes IS NOT NULL
                THEN 1.0 - (1.0 * lt.gzip_payload_bytes / mt.gzip_payload_bytes)
                ELSE NULL END AS mlt_after_gzip_saving_fraction,
            CASE WHEN lt.raw_payload_bytes > 0 AND lt.gzip_payload_bytes IS NOT NULL
                THEN 1.0 - (1.0 * lt.gzip_payload_bytes / lt.raw_payload_bytes)
                ELSE NULL END AS mlt_gzip_saving_fraction,
            CASE WHEN mt.raw_payload_bytes > 0 AND lt.gzip_payload_bytes IS NOT NULL
                THEN 1.0 - (1.0 * lt.gzip_payload_bytes / mt.raw_payload_bytes)
                ELSE NULL END AS mlt_plus_gzip_saving_fraction,

            CASE WHEN lt.raw_payload_bytes > 0
                THEN 1.0 * mt.raw_payload_bytes / lt.raw_payload_bytes
                ELSE NULL END AS mvt_to_mlt_raw_ratio,
            CASE WHEN lt.gzip_payload_bytes > 0
                THEN 1.0 * mt.gzip_payload_bytes / lt.gzip_payload_bytes
                ELSE NULL END AS mvt_gzip_to_mlt_gzip_ratio,

            -- Legacy metric: actual stored MLT vs actual stored MVT.
            CASE WHEN mt.stored_bytes > 0
                THEN 1.0 - (1.0 * lt.stored_bytes / mt.stored_bytes)
                ELSE NULL END AS mlt_saving_fraction,
            CASE WHEN lt.stored_bytes > 0
                THEN 1.0 * mt.stored_bytes / lt.stored_bytes
                ELSE NULL END AS mvt_to_mlt_size_ratio,

            CASE WHEN c.feature_instances > 0
                THEN 1.0 * mt.raw_payload_bytes / c.feature_instances ELSE NULL END AS mvt_raw_bytes_per_feature,
            CASE WHEN c.feature_instances > 0
                THEN 1.0 * lt.raw_payload_bytes / c.feature_instances ELSE NULL END AS mlt_raw_bytes_per_feature,
            CASE WHEN c.vertex_count > 0
                THEN 1.0 * mt.raw_payload_bytes / c.vertex_count ELSE NULL END AS mvt_raw_bytes_per_vertex,
            CASE WHEN c.vertex_count > 0
                THEN 1.0 * lt.raw_payload_bytes / c.vertex_count ELSE NULL END AS mlt_raw_bytes_per_vertex
        FROM maps m
        JOIN archives ma ON ma.map_id = m.id AND ma.format = 'MVT'
        JOIN archives la ON la.map_id = m.id AND la.format = 'MLT'
        JOIN tiles mt ON mt.archive_id = ma.id
        JOIN tiles lt ON lt.archive_id = la.id
                     AND lt.z = mt.z AND lt.x = mt.x AND lt.y = mt.y
        LEFT JOIN tile_content_stats c
            ON c.map_id = m.id AND c.z = mt.z AND c.x = mt.x AND c.y = mt.y;

        CREATE VIEW v_tile_layer_comparison AS
        WITH mlt_by_content_layer AS (
            SELECT
                archive_id,
                content_offset,
                content_length,
                layer_name,
                SUM(raw_frame_bytes) AS mlt_raw_layer_bytes,
                SUM(isolated_gzip_frame_bytes) AS mlt_isolated_gzip_layer_bytes,
                SUM(stream_count) AS mlt_stream_count,
                SUM(stream_payload_bytes) AS mlt_stream_payload_bytes,
                SUM(stream_overhead_bytes) AS mlt_stream_overhead_bytes,
                SUM(CASE WHEN parse_error IS NOT NULL THEN 1 ELSE 0 END) AS mlt_parse_errors
            FROM mlt_layers
            GROUP BY archive_id, content_offset, content_length, layer_name
        )
        SELECT
            m.name AS map_name,
            m.dataset_name,
            m.variant,
            m.density_factor,
            tl.z,
            tl.x,
            tl.y,
            tl.layer_name,
            tl.extent,
            tl.feature_instances,
            tl.vertex_count,
            tl.geometry_command_ints,
            tl.geometry_command_count,
            tl.tag_pairs,
            tl.mvt_raw_layer_bytes,
            tl.mvt_isolated_gzip_layer_bytes,
            tl.mvt_key_count,
            tl.mvt_value_count,
            tl.mvt_key_utf8_bytes,
            tl.mvt_value_proto_bytes,
            ml.mlt_raw_layer_bytes,
            ml.mlt_isolated_gzip_layer_bytes,
            ml.mlt_stream_count,
            ml.mlt_stream_payload_bytes,
            ml.mlt_stream_overhead_bytes,
            ml.mlt_parse_errors,
            CASE WHEN tl.mvt_raw_layer_bytes > 0 AND ml.mlt_raw_layer_bytes IS NOT NULL
                THEN 1.0 - (1.0 * ml.mlt_raw_layer_bytes / tl.mvt_raw_layer_bytes)
                ELSE NULL END AS mlt_raw_saving_fraction,
            CASE WHEN tl.mvt_isolated_gzip_layer_bytes > 0 AND ml.mlt_isolated_gzip_layer_bytes IS NOT NULL
                THEN 1.0 - (1.0 * ml.mlt_isolated_gzip_layer_bytes / tl.mvt_isolated_gzip_layer_bytes)
                ELSE NULL END AS isolated_gzip_mlt_saving_fraction
        FROM maps m
        JOIN tile_layers tl ON tl.map_id = m.id
        JOIN archives la ON la.map_id = m.id AND la.format = 'MLT'
        JOIN tiles lt ON lt.archive_id = la.id
                     AND lt.z = tl.z AND lt.x = tl.x AND lt.y = tl.y
        LEFT JOIN mlt_by_content_layer ml
               ON ml.archive_id = la.id
              AND ml.content_offset = lt.content_offset
              AND ml.content_length = lt.stored_bytes
              AND ml.layer_name = tl.layer_name;

        CREATE VIEW v_zoom_analysis AS
        WITH tile_cmp AS (
            SELECT * FROM v_tile_comparison
        )
        SELECT
            map_name,
            dataset_name,
            variant,
            density_factor,
            z,
            COUNT(*) AS tile_count,
            SUM(feature_instances) AS feature_instances,
            AVG(feature_instances) AS avg_features_per_tile,
            MAX(feature_instances) AS max_features_per_tile,
            SUM(vertex_count) AS vertex_count,
            AVG(vertex_count) AS avg_vertices_per_tile,
            SUM(geometry_command_ints) AS geometry_command_ints,
            SUM(geometry_command_count) AS geometry_command_count,
            SUM(tag_pairs) AS tag_pairs,
            SUM(mvt_stored_bytes) AS mvt_bytes,
            SUM(mlt_stored_bytes) AS mlt_bytes,
            SUM(mvt_raw_bytes) AS mvt_raw_bytes,
            SUM(mvt_gzip_bytes) AS mvt_gzip_bytes,
            SUM(mlt_raw_bytes) AS mlt_raw_bytes,
            SUM(mlt_gzip_bytes) AS mlt_gzip_bytes,
            AVG(mvt_stored_bytes) AS avg_mvt_tile_bytes,
            AVG(mlt_stored_bytes) AS avg_mlt_tile_bytes,
            MAX(mvt_stored_bytes) AS max_mvt_tile_bytes,
            MAX(mlt_stored_bytes) AS max_mlt_tile_bytes,
            CASE WHEN SUM(mvt_raw_bytes) > 0
                THEN 1.0 - (1.0 * SUM(mvt_gzip_bytes) / SUM(mvt_raw_bytes)) ELSE NULL END AS mvt_gzip_saving_fraction,
            CASE WHEN SUM(mvt_raw_bytes) > 0
                THEN 1.0 - (1.0 * SUM(mlt_raw_bytes) / SUM(mvt_raw_bytes)) ELSE NULL END AS mlt_raw_saving_fraction,
            CASE WHEN SUM(mvt_gzip_bytes) > 0
                THEN 1.0 - (1.0 * SUM(mlt_gzip_bytes) / SUM(mvt_gzip_bytes)) ELSE NULL END AS mlt_after_gzip_saving_fraction,
            CASE WHEN SUM(mvt_raw_bytes) > 0
                THEN 1.0 - (1.0 * SUM(mlt_gzip_bytes) / SUM(mvt_raw_bytes)) ELSE NULL END AS mlt_plus_gzip_saving_fraction,
            CASE WHEN SUM(mvt_stored_bytes) > 0
                THEN 1.0 - (1.0 * SUM(mlt_stored_bytes) / SUM(mvt_stored_bytes)) ELSE NULL END AS mlt_saving_fraction,
            CASE WHEN SUM(mlt_stored_bytes) > 0
                THEN 1.0 * SUM(mvt_stored_bytes) / SUM(mlt_stored_bytes) ELSE NULL END AS mvt_to_mlt_size_ratio
        FROM tile_cmp
        GROUP BY map_name, dataset_name, variant, density_factor, z;
        """
    )


def _insert_archive(connection: sqlite3.Connection, map_id: int, info: ArchiveInfo) -> int:
    header = info.header
    cursor = connection.execute(
        """
        INSERT INTO archives(
            map_id, format, path, file_bytes, pmtiles_version, tile_type_code,
            tile_compression, internal_compression, min_zoom, max_zoom,
            min_lon, min_lat, max_lon, max_lat, center_zoom, center_lon, center_lat,
            addressed_tiles_header, tile_entries_header, tile_contents_header,
            root_directory_bytes, metadata_bytes, leaf_directories_bytes, tile_data_bytes,
            clustered, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            map_id,
            info.format_name,
            str(info.path),
            info.path.stat().st_size,
            header.version,
            header.tile_type,
            header.tile_compression_name,
            header.internal_compression_name,
            header.min_zoom,
            header.max_zoom,
            header.min_lon,
            header.min_lat,
            header.max_lon,
            header.max_lat,
            header.center_zoom,
            header.center_lon,
            header.center_lat,
            header.addressed_tiles_count,
            header.tile_entries_count,
            header.tile_contents_count,
            header.root_length,
            header.metadata_length,
            header.leaf_directory_length,
            header.tile_data_length,
            int(header.clustered),
            json.dumps(info.metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cursor.lastrowid)


def _tile_layer_rows(
    map_id: int,
    z: int,
    x: int,
    y: int,
    summary: MVTTileSummary,
) -> tuple[list[tuple], list[tuple]]:
    layer_rows: list[tuple] = []
    geometry_rows: list[tuple] = []
    for layer in summary.layers:
        layer_rows.append(
            (
                map_id,
                z,
                x,
                y,
                layer.name,
                layer.extent,
                layer.version,
                len(layer.features),
                sum(feature.vertex_count for feature in layer.features),
                sum(feature.geometry_command_ints for feature in layer.features),
                sum(feature.geometry_command_count for feature in layer.features),
                sum(feature.tag_pairs for feature in layer.features),
                layer.raw_layer_bytes,
                layer.isolated_gzip_layer_bytes,
                layer.key_count,
                layer.value_count,
                layer.key_utf8_bytes,
                layer.value_proto_bytes,
            )
        )

        grouped: dict[str, list[int]] = {}
        for feature in layer.features:
            values = grouped.setdefault(feature.geometry_type, [0, 0, 0, 0, 0])
            values[0] += 1
            values[1] += feature.vertex_count
            values[2] += feature.geometry_command_ints
            values[3] += feature.geometry_command_count
            values[4] += feature.tag_pairs
        for geometry_type, values in grouped.items():
            geometry_rows.append(
                (
                    map_id,
                    z,
                    x,
                    y,
                    layer.name,
                    geometry_type,
                    values[0],
                    values[1],
                    values[2],
                    values[3],
                    values[4],
                )
            )
    return layer_rows, geometry_rows


def _flush_mvt_batches(
    connection: sqlite3.Connection,
    tile_rows: list[tuple],
    content_rows: list[tuple],
    tile_layer_rows: list[tuple],
    geometry_rows: list[tuple],
) -> None:
    if tile_rows:
        connection.executemany(
            """
            INSERT INTO tiles(
                archive_id, z, x, y, stored_bytes, raw_payload_bytes,
                gzip_payload_bytes, content_offset
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tile_rows,
        )
        tile_rows.clear()
    if content_rows:
        connection.executemany(
            """
            INSERT INTO tile_content_stats(
                map_id, z, x, y, feature_instances, vertex_count,
                geometry_command_ints, geometry_command_count, tag_pairs,
                layer_count, property_key_count, property_value_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            content_rows,
        )
        content_rows.clear()
    if tile_layer_rows:
        connection.executemany(
            """
            INSERT INTO tile_layers(
                map_id, z, x, y, layer_name, extent, mvt_version,
                feature_instances, vertex_count, geometry_command_ints,
                geometry_command_count, tag_pairs, mvt_raw_layer_bytes,
                mvt_isolated_gzip_layer_bytes, mvt_key_count, mvt_value_count,
                mvt_key_utf8_bytes, mvt_value_proto_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tile_layer_rows,
        )
        tile_layer_rows.clear()
    if geometry_rows:
        connection.executemany(
            """
            INSERT INTO tile_layer_stats(
                map_id, z, x, y, layer_name, geometry_type,
                feature_instances, vertex_count, geometry_command_ints,
                geometry_command_count, tag_pairs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            geometry_rows,
        )
        geometry_rows.clear()


def _scan_mvt_archive(
    connection: sqlite3.Connection,
    map_id: int,
    archive_id: int,
    info: ArchiveInfo,
    report: BuildReport,
    progress: Callable[[str], None] | None,
) -> dict[str, LayerTracker]:
    header = info.header
    layer_trackers: dict[str, LayerTracker] = {}
    tile_rows: list[tuple] = []
    content_rows: list[tuple] = []
    tile_layer_rows: list[tuple] = []
    geometry_rows: list[tuple] = []

    with info.path.open("rb") as handle:
        for run_index, run in enumerate(_iter_tile_runs_from_handle(handle, header), start=1):
            stored_payload = _read_section(handle, header.tile_data_offset + run.offset, run.length)
            raw_payload: bytes | None
            try:
                raw_payload = _decompress(
                    stored_payload,
                    header.tile_compression,
                    f"MVT tile payload in {info.path.name}",
                )
                summary = _parse_mvt_payload(raw_payload)
                parse_error = None
            except Exception as exc:
                raw_payload = None
                summary = MVTTileSummary(layers=())
                parse_error = f"{type(exc).__name__}: {exc}"

            raw_length = len(raw_payload) if raw_payload is not None else None
            gzip_length = _gzip_size(raw_payload) if raw_payload is not None else None

            for delta in range(run.run_length):
                z, x, y = tileid_to_zxy(run.tile_id + delta)
                tile_rows.append(
                    (archive_id, z, x, y, run.length, raw_length, gzip_length, run.offset)
                )
                content_rows.append(
                    (
                        map_id,
                        z,
                        x,
                        y,
                        summary.total_features,
                        summary.total_vertices,
                        summary.total_geometry_command_ints,
                        summary.total_geometry_command_count,
                        summary.total_tag_pairs,
                        len(summary.layers),
                        summary.total_key_count,
                        summary.total_value_count,
                    )
                )
                _layer_rows, _geometry_rows = _tile_layer_rows(map_id, z, x, y, summary)
                tile_layer_rows.extend(_layer_rows)
                geometry_rows.extend(_geometry_rows)
                _apply_tile_summary(layer_trackers, summary, z)
                report.tiles += 1
                report.feature_instances += summary.total_features

                if parse_error is not None:
                    connection.execute(
                        """
                        INSERT INTO analysis_errors(
                            map_id, archive_format, z, x, y, message
                        ) VALUES (?, 'MVT', ?, ?, ?, ?)
                        """,
                        (map_id, z, x, y, parse_error),
                    )
                    report.errors += 1

                if len(tile_rows) >= BATCH_SIZE:
                    _flush_mvt_batches(
                        connection, tile_rows, content_rows, tile_layer_rows, geometry_rows
                    )

            if progress and run_index % 10_000 == 0:
                progress(f"{info.path.name}: processed {run_index:,} tile runs")

    _flush_mvt_batches(connection, tile_rows, content_rows, tile_layer_rows, geometry_rows)
    return layer_trackers


def _mlt_layer_row(
    archive_id: int,
    content_offset: int,
    content_length: int,
    layer: MLTLayerObservation,
) -> tuple:
    payload_bytes = sum(stream.payload_bytes for stream in layer.streams)
    overhead_bytes = sum(stream.header_bytes for stream in layer.streams)
    return (
        archive_id,
        content_offset,
        content_length,
        layer.layer_index,
        layer.name,
        layer.tag,
        layer.extent,
        layer.column_count,
        layer.feature_count,
        layer.raw_frame_bytes,
        layer.isolated_gzip_frame_bytes,
        layer.metadata_bytes,
        layer.data_bytes,
        len(layer.streams),
        payload_bytes,
        overhead_bytes,
        layer.parse_error,
    )


def _mlt_stream_rows(
    archive_id: int,
    content_offset: int,
    content_length: int,
    layer: MLTLayerObservation,
) -> list[tuple]:
    return [
        (
            archive_id,
            content_offset,
            content_length,
            layer.layer_index,
            layer.name,
            stream.column_index,
            stream.column_name,
            stream.column_type,
            stream.stream_index,
            stream.stream_type_code,
            stream.stream_category,
            stream.stream_subtype,
            stream.stream_role,
            stream.encoding_code,
            stream.logical_encoding,
            stream.physical_encoding,
            stream.num_values,
            stream.payload_bytes,
            stream.header_bytes,
            stream.total_bytes,
            stream.runs,
            stream.num_rle_values,
            stream.morton_bits,
            stream.morton_shift,
        )
        for stream in layer.streams
    ]


def _flush_mlt_batches(
    connection: sqlite3.Connection,
    tile_rows: list[tuple],
    layer_rows: list[tuple],
    stream_rows: list[tuple],
) -> None:
    if tile_rows:
        connection.executemany(
            """
            INSERT INTO tiles(
                archive_id, z, x, y, stored_bytes, raw_payload_bytes,
                gzip_payload_bytes, content_offset
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tile_rows,
        )
        tile_rows.clear()
    if layer_rows:
        connection.executemany(
            """
            INSERT INTO mlt_layers(
                archive_id, content_offset, content_length, layer_index,
                layer_name, frame_tag, extent, column_count, feature_count,
                raw_frame_bytes, isolated_gzip_frame_bytes, metadata_bytes,
                data_bytes, stream_count, stream_payload_bytes,
                stream_overhead_bytes, parse_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            layer_rows,
        )
        layer_rows.clear()
    if stream_rows:
        connection.executemany(
            """
            INSERT INTO mlt_streams(
                archive_id, content_offset, content_length, layer_index,
                layer_name, column_index, column_name, column_type, stream_index,
                stream_type_code, stream_category, stream_subtype, stream_role,
                encoding_code, logical_encoding, physical_encoding, num_values,
                payload_bytes, header_bytes, total_bytes, runs, num_rle_values,
                morton_bits, morton_shift
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            stream_rows,
        )
        stream_rows.clear()


def _scan_mlt_archive(
    connection: sqlite3.Connection,
    map_id: int,
    archive_id: int,
    info: ArchiveInfo,
    report: BuildReport,
    progress: Callable[[str], None] | None,
) -> None:
    header = info.header
    tile_rows: list[tuple] = []
    mlt_layer_rows: list[tuple] = []
    mlt_stream_rows: list[tuple] = []
    inspected_contents: set[tuple[int, int]] = set()

    with info.path.open("rb") as handle:
        for run_index, run in enumerate(_iter_tile_runs_from_handle(handle, header), start=1):
            stored_payload = _read_section(handle, header.tile_data_offset + run.offset, run.length)
            try:
                raw_payload = _decompress(
                    stored_payload,
                    header.tile_compression,
                    f"MLT tile payload in {info.path.name}",
                )
                raw_length = len(raw_payload)
                gzip_length = _gzip_size(raw_payload)
                payload_error = None
            except Exception as exc:
                raw_payload = None
                raw_length = None
                gzip_length = None
                payload_error = f"{type(exc).__name__}: {exc}"

            first_zxy = tileid_to_zxy(run.tile_id)
            if payload_error is not None:
                report.warnings.append(
                    f"Could not decompress {info.path.name} run {run_index}: {payload_error}"
                )
                connection.execute(
                    """
                    INSERT INTO analysis_errors(
                        map_id, archive_format, z, x, y, message
                    ) VALUES (?, 'MLT', ?, ?, ?, ?)
                    """,
                    (map_id, first_zxy[0], first_zxy[1], first_zxy[2], payload_error),
                )
                report.errors += 1

            content_key = (run.offset, run.length)
            if raw_payload is not None and content_key not in inspected_contents:
                inspected_contents.add(content_key)
                try:
                    observation = _parse_mlt_payload(raw_payload)
                except Exception as exc:
                    observation = MLTTileObservation(layers=())
                    _message = f"{type(exc).__name__}: {exc}"
                    connection.execute(
                        """
                        INSERT INTO analysis_errors(
                            map_id, archive_format, z, x, y, message
                        ) VALUES (?, 'MLT', ?, ?, ?, ?)
                        """,
                        (map_id, first_zxy[0], first_zxy[1], first_zxy[2], _message),
                    )
                    report.errors += 1

                for layer in observation.layers:
                    mlt_layer_rows.append(
                        _mlt_layer_row(archive_id, run.offset, run.length, layer)
                    )
                    mlt_stream_rows.extend(
                        _mlt_stream_rows(archive_id, run.offset, run.length, layer)
                    )
                    if layer.parse_error is not None:
                        connection.execute(
                            """
                            INSERT INTO analysis_errors(
                                map_id, archive_format, z, x, y, message
                            ) VALUES (?, 'MLT', ?, ?, ?, ?)
                            """,
                            (
                                map_id,
                                first_zxy[0],
                                first_zxy[1],
                                first_zxy[2],
                                f"layer {layer.layer_index}: {layer.parse_error}",
                            ),
                        )
                        report.errors += 1

            for delta in range(run.run_length):
                z, x, y = tileid_to_zxy(run.tile_id + delta)
                tile_rows.append(
                    (archive_id, z, x, y, run.length, raw_length, gzip_length, run.offset)
                )
                report.tiles += 1

            if (
                len(tile_rows) >= BATCH_SIZE
                or len(mlt_stream_rows) >= BATCH_SIZE * 4
                or len(mlt_layer_rows) >= BATCH_SIZE
            ):
                _flush_mlt_batches(connection, tile_rows, mlt_layer_rows, mlt_stream_rows)

            if progress and run_index % 10_000 == 0:
                progress(f"{info.path.name}: processed {run_index:,} tile runs")

    _flush_mlt_batches(connection, tile_rows, mlt_layer_rows, mlt_stream_rows)


def _write_layer_summaries(
    connection: sqlite3.Connection,
    map_id: int,
    layer_trackers: dict[str, LayerTracker],
) -> None:
    layer_rows: list[tuple] = []
    property_rows: list[tuple] = []
    property_value_rows: list[tuple] = []
    semantic_rows: list[tuple] = []

    for layer_name, tracker in sorted(layer_trackers.items()):
        semantic_key = _semantic_key_for_layer(tracker)
        layer_rows.append(
            (
                map_id,
                layer_name,
                tracker.feature_instances,
                tracker.first_zoom,
                tracker.last_zoom,
                tracker.min_extent,
                tracker.max_extent,
                ",".join(str(value) for value in sorted(tracker.versions)),
                semantic_key,
                tracker.geom_counts.get("POINT", 0),
                tracker.geom_counts.get("LINESTRING", 0),
                tracker.geom_counts.get("POLYGON", 0),
                sum(
                    count
                    for geom, count in tracker.geom_counts.items()
                    if geom not in {"POINT", "LINESTRING", "POLYGON"}
                ),
            )
        )

        for key, prop in sorted(tracker.properties.items()):
            property_rows.append(
                (
                    map_id,
                    layer_name,
                    key,
                    prop.occurrences,
                    json.dumps(dict(sorted(prop.value_types.items())), ensure_ascii=False),
                    prop.distinct_values_seen,
                    int(prop.high_cardinality),
                    json.dumps(prop.samples, ensure_ascii=False),
                    prop.first_zoom,
                    prop.last_zoom,
                )
            )
            if not prop.high_cardinality:
                for (zoom, geometry_type, property_value), count in prop.detail.items():
                    property_value_rows.append(
                        (
                            map_id,
                            layer_name,
                            key,
                            property_value,
                            geometry_type,
                            zoom,
                            count,
                        )
                    )

        if semantic_key is not None:
            prop = tracker.properties[semantic_key]
            observed_by_zoom_geom: Counter[tuple[int, str]] = Counter()
            for (zoom, geometry_type, semantic_value), count in prop.detail.items():
                semantic_rows.append(
                    (
                        map_id,
                        layer_name,
                        semantic_key,
                        semantic_value,
                        geometry_type,
                        zoom,
                        count,
                    )
                )
                observed_by_zoom_geom[(zoom, geometry_type)] += count
            for (zoom, geometry_type), total_count in tracker.zoom_geom_counts.items():
                missing = total_count - observed_by_zoom_geom[(zoom, geometry_type)]
                if missing > 0:
                    semantic_rows.append(
                        (
                            map_id,
                            layer_name,
                            semantic_key,
                            "<missing>",
                            geometry_type,
                            zoom,
                            missing,
                        )
                    )
        else:
            for (zoom, geometry_type), count in tracker.zoom_geom_counts.items():
                semantic_rows.append(
                    (
                        map_id,
                        layer_name,
                        "<layer>",
                        layer_name,
                        geometry_type,
                        zoom,
                        count,
                    )
                )

    if layer_rows:
        connection.executemany(
            """
            INSERT INTO layers(
                map_id, layer_name, feature_instances, min_zoom, max_zoom, min_extent, max_extent,
                mvt_versions, semantic_key, point_instances, linestring_instances,
                polygon_instances, unknown_instances
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            layer_rows,
        )
    if property_rows:
        connection.executemany(
            """
            INSERT INTO properties(
                map_id, layer_name, property_key, feature_occurrences, value_types,
                distinct_values_capped, high_cardinality, sample_values_json, min_zoom, max_zoom
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            property_rows,
        )
    if property_value_rows:
        connection.executemany(
            """
            INSERT INTO property_values(
                map_id, layer_name, property_key, property_value, geometry_type, zoom, feature_instances
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            property_value_rows,
        )
    if semantic_rows:
        connection.executemany(
            """
            INSERT INTO semantic_types(
                map_id, layer_name, semantic_key, semantic_value, geometry_type, zoom, feature_instances
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            semantic_rows,
        )


def _validate_pair(connection: sqlite3.Connection, map_id: int, mvt_archive_id: int, mlt_archive_id: int) -> tuple[int, int]:
    mvt_count = int(
        connection.execute("SELECT COUNT(*) FROM tiles WHERE archive_id = ?", (mvt_archive_id,)).fetchone()[0]
    )
    mlt_count = int(
        connection.execute("SELECT COUNT(*) FROM tiles WHERE archive_id = ?", (mlt_archive_id,)).fetchone()[0]
    )
    missing_in_mlt = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM tiles mvt
            LEFT JOIN tiles mlt
              ON mlt.archive_id = ? AND mlt.z = mvt.z AND mlt.x = mvt.x AND mlt.y = mvt.y
            WHERE mvt.archive_id = ? AND mlt.archive_id IS NULL
            """,
            (mlt_archive_id, mvt_archive_id),
        ).fetchone()[0]
    )
    missing_in_mvt = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM tiles mlt
            LEFT JOIN tiles mvt
              ON mvt.archive_id = ? AND mvt.z = mlt.z AND mvt.x = mlt.x AND mvt.y = mlt.y
            WHERE mlt.archive_id = ? AND mvt.archive_id IS NULL
            """,
            (mvt_archive_id, mlt_archive_id),
        ).fetchone()[0]
    )
    connection.execute(
        """
        INSERT INTO pair_validation(
            map_id, mvt_tile_count, mlt_tile_count, missing_in_mlt, missing_in_mvt, same_tile_coordinates
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            map_id,
            mvt_count,
            mlt_count,
            missing_in_mlt,
            missing_in_mvt,
            int(missing_in_mlt == 0 and missing_in_mvt == 0),
        ),
    )
    return missing_in_mlt, missing_in_mvt



def _map_identity(name: str) -> tuple[str, str, int]:
    """Split a logical pair name into source dataset and density/overzoom variant."""
    match = re.search(r"(?i)_(standard|dense4|dense16)$", name)
    if match:
        variant = match.group(1).lower()
        factor = {"standard": 1, "dense4": 4, "dense16": 16}[variant]
        return name[: match.start()], variant, factor

    match = re.search(r"(?i)_(oz|sz)(2|4)$", name)
    if match:
        variant = f"{match.group(1).lower()}{match.group(2)}"
        return name[: match.start()], variant, int(match.group(2))

    return name, "base", 1


def build_working_database(
    input_dir: str | Path,
    db_path: str | Path,
    *,
    progress: Callable[[str], None] | None = print,
    pair_names: set[str] | None = None,
) -> BuildReport:
    """Measure archives in a disposable DuckDB workspace for Parquet publication."""
    input_dir = Path(input_dir).resolve()
    db_path = Path(db_path).resolve()
    pairs = discover_pairs(input_dir)
    if pair_names is not None:
        pairs = [pair for pair in pairs if pair.name in pair_names]
        missing = pair_names - {pair.name for pair in pairs}
        if missing:
            raise FileNotFoundError(f"Missing registered archive pairs: {sorted(missing)}")
    if not pairs:
        raise FileNotFoundError(f"No paired MVT/MLT PMTiles archives found under {input_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_name(db_path.name + ".tmp")
    for candidate in (temp_path, Path(str(temp_path) + "-wal"), Path(str(temp_path) + "-shm")):
        if candidate.exists():
            candidate.unlink()

    report = BuildReport(db_path=db_path, input_dir=input_dir)
    from .tile_store import Connection
    connection = Connection(temp_path)
    try:
        _create_schema(connection)
        for pair_index, pair in enumerate(pairs, start=1):
            if progress:
                progress(f"[{pair_index}/{len(pairs)}] {pair.name}: inspecting archives")
            mvt_info = inspect_archive(pair.mvt_path)
            mlt_info = inspect_archive(pair.mlt_path)
            if mvt_info.format_name != FORMAT_MVT:
                raise ValueError(f"{pair.mvt_path} is {mvt_info.format_name}, not MVT")
            if mlt_info.format_name != FORMAT_MLT:
                raise ValueError(f"{pair.mlt_path} is {mlt_info.format_name}, not MLT")

            dataset_name, variant, density_factor = _map_identity(pair.name)
            cursor = connection.execute(
                """
                INSERT INTO maps(
                    name, dataset_name, variant, density_factor,
                    semantics_source, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pair.name,
                    dataset_name,
                    variant,
                    density_factor,
                    "paired MVT; MVT semantics are authoritative and MLT is the encoded equivalent",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            map_id = int(cursor.lastrowid)
            mvt_archive_id = _insert_archive(connection, map_id, mvt_info)
            mlt_archive_id = _insert_archive(connection, map_id, mlt_info)
            report.maps += 1
            report.archives += 2

            if progress:
                progress(f"[{pair_index}/{len(pairs)}] {pair.name}: scanning MVT semantics and physical layout")
            layer_trackers = _scan_mvt_archive(
                connection, map_id, mvt_archive_id, mvt_info, report, progress
            )
            _write_layer_summaries(connection, map_id, layer_trackers)

            if progress:
                progress(f"[{pair_index}/{len(pairs)}] {pair.name}: scanning MLT physical layout")
            _scan_mlt_archive(
                connection, map_id, mlt_archive_id, mlt_info, report, progress
            )

            missing_in_mlt, missing_in_mvt = _validate_pair(
                connection, map_id, mvt_archive_id, mlt_archive_id
            )
            if missing_in_mlt or missing_in_mvt:
                warning = (
                    f"{pair.name}: tile-coordinate mismatch: {missing_in_mlt} MVT tiles absent in MLT, "
                    f"{missing_in_mvt} MLT tiles absent in MVT"
                )
                report.warnings.append(warning)
                if progress:
                    progress("WARNING: " + warning)
            connection.commit()

        _create_indexes_and_views(connection)
        connection.commit()
    except Exception:
        connection.close()
        if temp_path.exists():
            temp_path.unlink()
        raise
    else:
        connection.close()

    os.replace(temp_path, db_path)
    if progress:
        progress(f"Analysis written to {db_path}")
    return report


def _query(db_path: str | Path, sql: str, params: Sequence[object] = ()) -> list[dict]:
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    from .tile_store import connect
    connection = connect(db_path)
    try:
        cursor = connection.execute(sql, params)
        names = [c[0] for c in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def list_maps(db_path: str | Path | None = None) -> list[str]:
    _, default_db = get_default_paths()
    rows = _query(db_path or default_db, "SELECT name FROM maps ORDER BY name")
    return [row["name"] for row in rows]


def get_map_overview(db_path: str | Path, map_name: str) -> list[dict]:
    return _query(
        db_path,
        """
        SELECT
            m.name AS map_name,
            m.dataset_name,
            m.variant,
            m.density_factor,
            a.format,
            a.path,
            a.file_bytes,
            a.tile_data_bytes,
            a.tile_compression,
            a.internal_compression,
            a.min_zoom,
            a.max_zoom,
            a.min_lon,
            a.min_lat,
            a.max_lon,
            a.max_lat,
            a.center_lon,
            a.center_lat,
            a.center_zoom,
            a.addressed_tiles_header,
            a.tile_entries_header,
            a.tile_contents_header,
            COALESCE(SUM(t.raw_payload_bytes), 0) AS addressed_raw_payload_bytes,
            COALESCE(SUM(t.gzip_payload_bytes), 0) AS addressed_gzip_payload_bytes,
            COALESCE(SUM(t.stored_bytes), 0) AS addressed_stored_payload_bytes,
            p.same_tile_coordinates,
            p.missing_in_mlt,
            p.missing_in_mvt
        FROM maps m
        JOIN archives a ON a.map_id = m.id
        JOIN pair_validation p ON p.map_id = m.id
        LEFT JOIN tiles t ON t.archive_id = a.id
        WHERE m.name = ?
        GROUP BY a.id
        ORDER BY CASE a.format WHEN 'MVT' THEN 0 ELSE 1 END
        """,
        (map_name,),
    )


def get_variant_overview(db_path: str | Path, dataset_name: str | None = None) -> list[dict]:
    where = "WHERE m.dataset_name = ?" if dataset_name is not None else ""
    params: tuple[object, ...] = (dataset_name,) if dataset_name is not None else ()
    return _query(
        db_path,
        f"""
        WITH totals AS (
            SELECT
                map_name,
                dataset_name,
                variant,
                density_factor,
                COUNT(*) AS tile_count,
                SUM(feature_instances) AS feature_instances,
                SUM(vertex_count) AS vertex_count,
                SUM(mvt_raw_bytes) AS mvt_raw_bytes,
                SUM(mvt_gzip_bytes) AS mvt_gzip_bytes,
                SUM(mlt_raw_bytes) AS mlt_raw_bytes,
                SUM(mlt_gzip_bytes) AS mlt_gzip_bytes
            FROM v_tile_comparison
            GROUP BY map_name, dataset_name, variant, density_factor
        )
        SELECT
            t.*,
            CASE WHEN t.mvt_raw_bytes > 0
                THEN 1.0 - 1.0 * t.mvt_gzip_bytes / t.mvt_raw_bytes END AS mvt_gzip_saving_fraction,
            CASE WHEN t.mvt_raw_bytes > 0
                THEN 1.0 - 1.0 * t.mlt_raw_bytes / t.mvt_raw_bytes END AS mlt_raw_saving_fraction,
            CASE WHEN t.mvt_gzip_bytes > 0
                THEN 1.0 - 1.0 * t.mlt_gzip_bytes / t.mvt_gzip_bytes END AS mlt_after_gzip_saving_fraction,
            CASE WHEN t.mvt_raw_bytes > 0
                THEN 1.0 - 1.0 * t.mlt_gzip_bytes / t.mvt_raw_bytes END AS mlt_plus_gzip_saving_fraction
        FROM totals t
        JOIN maps m ON m.name = t.map_name
        {where}
        ORDER BY t.dataset_name, t.density_factor, t.variant
        """,
        params,
    )


def get_zoom_analysis(db_path: str | Path, map_name: str) -> list[dict]:
    return _query(
        db_path,
        "SELECT * FROM v_zoom_analysis WHERE map_name = ? ORDER BY z",
        (map_name,),
    )


def get_tile_compression_analysis(
    db_path: str | Path,
    map_name: str,
    *,
    zoom: int | None = None,
    limit: int | None = None,
) -> list[dict]:
    where = "map_name = ?"
    params: list[object] = [map_name]
    if zoom is not None:
        where += " AND z = ?"
        params.append(int(zoom))
    sql = f"""
        SELECT *
        FROM v_tile_comparison
        WHERE {where}
        ORDER BY z, y, x
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(1, int(limit)))
    return _query(db_path, sql, tuple(params))


def get_compression_buckets(db_path: str | Path, map_name: str) -> list[dict]:
    return _query(
        db_path,
        """
        WITH base AS (
            SELECT *,
                CASE
                    WHEN feature_instances = 0 THEN '0'
                    WHEN feature_instances < 10 THEN '1-9'
                    WHEN feature_instances < 50 THEN '10-49'
                    WHEN feature_instances < 200 THEN '50-199'
                    WHEN feature_instances < 1000 THEN '200-999'
                    WHEN feature_instances < 5000 THEN '1000-4999'
                    ELSE '5000+'
                END AS feature_bucket,
                CASE
                    WHEN vertex_count = 0 THEN '0'
                    WHEN vertex_count < 100 THEN '1-99'
                    WHEN vertex_count < 500 THEN '100-499'
                    WHEN vertex_count < 2000 THEN '500-1999'
                    WHEN vertex_count < 10000 THEN '2000-9999'
                    WHEN vertex_count < 50000 THEN '10000-49999'
                    ELSE '50000+'
                END AS vertex_bucket
            FROM v_tile_comparison
            WHERE map_name = ?
        ),
        feature_groups AS (
            SELECT
                'features' AS dimension,
                feature_bucket AS bucket,
                COUNT(*) AS tile_count,
                AVG(feature_instances) AS avg_features,
                AVG(vertex_count) AS avg_vertices,
                AVG(layer_count) AS avg_layers,
                AVG(mvt_gzip_saving_fraction) AS avg_mvt_gzip_saving_fraction,
                AVG(mlt_raw_saving_fraction) AS avg_mlt_raw_saving_fraction,
                AVG(mlt_after_gzip_saving_fraction) AS avg_mlt_after_gzip_saving_fraction,
                AVG(mlt_plus_gzip_saving_fraction) AS avg_mlt_plus_gzip_saving_fraction
            FROM base
            GROUP BY feature_bucket
        ),
        vertex_groups AS (
            SELECT
                'vertices' AS dimension,
                vertex_bucket AS bucket,
                COUNT(*) AS tile_count,
                AVG(feature_instances) AS avg_features,
                AVG(vertex_count) AS avg_vertices,
                AVG(layer_count) AS avg_layers,
                AVG(mvt_gzip_saving_fraction) AS avg_mvt_gzip_saving_fraction,
                AVG(mlt_raw_saving_fraction) AS avg_mlt_raw_saving_fraction,
                AVG(mlt_after_gzip_saving_fraction) AS avg_mlt_after_gzip_saving_fraction,
                AVG(mlt_plus_gzip_saving_fraction) AS avg_mlt_plus_gzip_saving_fraction
            FROM base
            GROUP BY vertex_bucket
        )
        SELECT * FROM feature_groups
        UNION ALL
        SELECT * FROM vertex_groups
        """,
        (map_name,),
    )


def get_layer_analysis(db_path: str | Path, map_name: str) -> list[dict]:
    return _query(
        db_path,
        """
        WITH compression AS (
            SELECT
                layer_name,
                COUNT(*) AS tile_layer_instances,
                SUM(feature_instances) AS compression_feature_instances,
                SUM(vertex_count) AS vertex_count,
                SUM(geometry_command_ints) AS geometry_command_ints,
                SUM(tag_pairs) AS tag_pairs,
                SUM(mvt_raw_layer_bytes) AS mvt_raw_layer_bytes,
                SUM(mvt_isolated_gzip_layer_bytes) AS mvt_isolated_gzip_layer_bytes,
                SUM(mlt_raw_layer_bytes) AS mlt_raw_layer_bytes,
                SUM(mlt_isolated_gzip_layer_bytes) AS mlt_isolated_gzip_layer_bytes,
                SUM(mvt_key_count) AS mvt_key_count,
                SUM(mvt_value_count) AS mvt_value_count,
                SUM(mvt_key_utf8_bytes) AS mvt_key_utf8_bytes,
                SUM(mvt_value_proto_bytes) AS mvt_value_proto_bytes,
                SUM(mlt_stream_count) AS mlt_stream_count,
                SUM(mlt_stream_payload_bytes) AS mlt_stream_payload_bytes,
                SUM(mlt_stream_overhead_bytes) AS mlt_stream_overhead_bytes,
                SUM(COALESCE(mlt_parse_errors, 0)) AS mlt_parse_errors
            FROM v_tile_layer_comparison
            WHERE map_name = ?
            GROUP BY layer_name
        )
        SELECT
            l.layer_name,
            l.semantic_key,
            l.min_zoom,
            l.max_zoom,
            l.min_extent,
            l.max_extent,
            l.mvt_versions,
            l.feature_instances,
            l.point_instances,
            l.linestring_instances,
            l.polygon_instances,
            l.unknown_instances,
            c.tile_layer_instances,
            c.vertex_count,
            c.geometry_command_ints,
            c.tag_pairs,
            c.mvt_raw_layer_bytes,
            c.mvt_isolated_gzip_layer_bytes,
            c.mlt_raw_layer_bytes,
            c.mlt_isolated_gzip_layer_bytes,
            c.mvt_key_count,
            c.mvt_value_count,
            c.mvt_key_utf8_bytes,
            c.mvt_value_proto_bytes,
            c.mlt_stream_count,
            c.mlt_stream_payload_bytes,
            c.mlt_stream_overhead_bytes,
            c.mlt_parse_errors,
            CASE WHEN c.mvt_raw_layer_bytes > 0 AND c.mlt_raw_layer_bytes IS NOT NULL
                THEN 1.0 - 1.0 * c.mlt_raw_layer_bytes / c.mvt_raw_layer_bytes END AS mlt_raw_saving_fraction,
            CASE WHEN c.mvt_isolated_gzip_layer_bytes > 0 AND c.mlt_isolated_gzip_layer_bytes IS NOT NULL
                THEN 1.0 - 1.0 * c.mlt_isolated_gzip_layer_bytes / c.mvt_isolated_gzip_layer_bytes END AS isolated_gzip_mlt_saving_fraction,
            CASE WHEN c.vertex_count > 0
                THEN 1.0 * c.mlt_raw_layer_bytes / c.vertex_count END AS mlt_raw_bytes_per_vertex
        FROM layers l
        JOIN maps m ON m.id = l.map_id
        LEFT JOIN compression c ON c.layer_name = l.layer_name
        WHERE m.name = ?
        ORDER BY l.feature_instances DESC, l.layer_name
        """,
        (map_name, map_name),
    )


def get_mlt_stream_analysis(
    db_path: str | Path,
    map_name: str,
    *,
    layer_name: str | None = None,
) -> list[dict]:
    layer_filter = "AND s.layer_name = ?" if layer_name is not None else ""
    params: tuple[object, ...] = (map_name, layer_name) if layer_name is not None else (map_name,)
    return _query(
        db_path,
        f"""
        WITH weighted AS (
            SELECT
                s.layer_name,
                s.column_name,
                s.column_type,
                s.stream_role,
                s.logical_encoding,
                s.physical_encoding,
                s.num_values,
                s.payload_bytes,
                s.header_bytes,
                s.total_bytes,
                s.runs,
                s.num_rle_values
            FROM maps m
            JOIN archives a ON a.map_id = m.id AND a.format = 'MLT'
            JOIN tiles t ON t.archive_id = a.id
            JOIN mlt_streams s
              ON s.archive_id = t.archive_id
             AND s.content_offset = t.content_offset
             AND s.content_length = t.stored_bytes
            WHERE m.name = ?
            {layer_filter}
        ),
        tile_total AS (
            SELECT SUM(raw_payload_bytes) AS total_raw
            FROM maps m
            JOIN archives a ON a.map_id = m.id AND a.format = 'MLT'
            JOIN tiles t ON t.archive_id = a.id
            WHERE m.name = ?
        )
        SELECT
            w.layer_name,
            w.column_name,
            w.column_type,
            w.stream_role,
            w.logical_encoding,
            w.physical_encoding,
            COUNT(*) AS stream_instances,
            SUM(w.num_values) AS values_count,
            SUM(w.payload_bytes) AS payload_bytes,
            SUM(w.header_bytes) AS header_bytes,
            SUM(w.total_bytes) AS total_stream_bytes,
            CASE WHEN SUM(w.num_values) > 0
                THEN 1.0 * SUM(w.payload_bytes) / SUM(w.num_values) END AS payload_bytes_per_value,
            CASE WHEN tt.total_raw > 0
                THEN 1.0 * SUM(w.total_bytes) / tt.total_raw END AS share_of_mlt_raw_payload
        FROM weighted w
        CROSS JOIN tile_total tt
        GROUP BY
            w.layer_name, w.column_name, w.column_type,
            w.stream_role, w.logical_encoding, w.physical_encoding
        ORDER BY total_stream_bytes DESC, w.layer_name, w.column_name
        """,
        params + (map_name,),
    )


def get_semantic_types(db_path: str | Path, map_name: str) -> list[dict]:
    return _query(
        db_path,
        """
        SELECT
            s.layer_name,
            s.semantic_key,
            s.semantic_value,
            s.geometry_type,
            MIN(s.zoom) AS min_zoom,
            MAX(s.zoom) AS max_zoom,
            SUM(s.feature_instances) AS feature_instances
        FROM semantic_types s
        JOIN maps m ON m.id = s.map_id
        WHERE m.name = ?
        GROUP BY s.layer_name, s.semantic_key, s.semantic_value, s.geometry_type
        ORDER BY s.layer_name, feature_instances DESC, s.semantic_value
        """,
        (map_name,),
    )


def get_property_schema(db_path: str | Path, map_name: str) -> list[dict]:
    return _query(
        db_path,
        """
        SELECT
            p.layer_name,
            p.property_key,
            p.feature_occurrences,
            p.value_types,
            p.distinct_values_capped,
            p.high_cardinality,
            p.sample_values_json,
            p.min_zoom,
            p.max_zoom
        FROM properties p
        JOIN maps m ON m.id = p.map_id
        WHERE m.name = ?
        ORDER BY p.layer_name, p.feature_occurrences DESC, p.property_key
        """,
        (map_name,),
    )


def get_property_values(
    db_path: str | Path,
    map_name: str,
    layer_name: str | None = None,
) -> list[dict]:
    if layer_name is None:
        return _query(
            db_path,
            """
            SELECT
                pv.layer_name,
                pv.property_key,
                pv.property_value,
                pv.geometry_type,
                MIN(pv.zoom) AS min_zoom,
                MAX(pv.zoom) AS max_zoom,
                SUM(pv.feature_instances) AS feature_instances
            FROM property_values pv
            JOIN maps m ON m.id = pv.map_id
            WHERE m.name = ?
            GROUP BY pv.layer_name, pv.property_key, pv.property_value, pv.geometry_type
            ORDER BY pv.layer_name, pv.property_key, feature_instances DESC, pv.property_value
            """,
            (map_name,),
        )
    return _query(
        db_path,
        """
        SELECT
            pv.layer_name,
            pv.property_key,
            pv.property_value,
            pv.geometry_type,
            MIN(pv.zoom) AS min_zoom,
            MAX(pv.zoom) AS max_zoom,
            SUM(pv.feature_instances) AS feature_instances
        FROM property_values pv
        JOIN maps m ON m.id = pv.map_id
        WHERE m.name = ? AND pv.layer_name = ?
        GROUP BY pv.layer_name, pv.property_key, pv.property_value, pv.geometry_type
        ORDER BY pv.property_key, feature_instances DESC, pv.property_value
        """,
        (map_name, layer_name),
    )


def get_analysis_errors(db_path: str | Path, map_name: str | None = None) -> list[dict]:
    if map_name is None:
        return _query(
            db_path,
            """
            SELECT m.name AS map_name, e.archive_format, e.z, e.x, e.y, e.message
            FROM analysis_errors e LEFT JOIN maps m ON m.id = e.map_id
            ORDER BY e.id
            """,
        )
    return _query(
        db_path,
        """
        SELECT m.name AS map_name, e.archive_format, e.z, e.x, e.y, e.message
        FROM analysis_errors e JOIN maps m ON m.id = e.map_id
        WHERE m.name = ?
        ORDER BY e.id
        """,
        (map_name,),
    )


def _lon_to_world_px(lon: float, zoom: int, tile_size: int) -> float:
    world_size = (1 << zoom) * tile_size
    return (lon + 180.0) / 360.0 * world_size


def _lat_to_world_px(lat: float, zoom: int, tile_size: int) -> float:
    lat = max(-85.05112878, min(85.05112878, lat))
    radians = math.radians(lat)
    world_size = (1 << zoom) * tile_size
    mercator = math.log(math.tan(math.pi / 4.0 + radians / 2.0))
    return (1.0 - mercator / math.pi) / 2.0 * world_size


def viewport_tile_coordinates(
    center_lon: float,
    center_lat: float,
    zoom: int,
    width_px: int,
    height_px: int,
    tile_size: int = 512,
) -> list[tuple[int, int]]:
    if width_px <= 0 or height_px <= 0 or tile_size <= 0:
        raise ValueError("Viewport width, height, and tile_size must be positive")
    if zoom < 0 or zoom > 31:
        raise ValueError("Zoom must be between 0 and 31")

    n = 1 << zoom
    center_x = _lon_to_world_px(center_lon, zoom, tile_size)
    center_y = _lat_to_world_px(center_lat, zoom, tile_size)
    min_x = math.floor((center_x - width_px / 2.0) / tile_size)
    max_x = math.floor((center_x + width_px / 2.0 - 1e-9) / tile_size)
    min_y = max(0, math.floor((center_y - height_px / 2.0) / tile_size))
    max_y = min(n - 1, math.floor((center_y + height_px / 2.0 - 1e-9) / tile_size))

    result: list[tuple[int, int]] = []
    for x_unwrapped in range(min_x, max_x + 1):
        x = x_unwrapped % n
        for y in range(min_y, max_y + 1):
            result.append((x, y))
    return sorted(set(result))


def estimate_viewport(
    db_path: str | Path,
    map_name: str,
    *,
    center_lon: float,
    center_lat: float,
    zoom: int,
    width_px: int,
    height_px: int,
    tile_size: int = 512,
) -> dict:
    coordinates = viewport_tile_coordinates(
        center_lon=center_lon,
        center_lat=center_lat,
        zoom=zoom,
        width_px=width_px,
        height_px=height_px,
        tile_size=tile_size,
    )
    if not coordinates:
        return {
            "map_name": map_name,
            "zoom": zoom,
            "viewport_tiles": 0,
            "present_tiles": 0,
            "feature_instances": 0,
            "mvt_bytes": 0,
            "mlt_bytes": 0,
            "mvt_raw_bytes": 0,
            "mvt_gzip_bytes": 0,
            "mlt_raw_bytes": 0,
            "mlt_gzip_bytes": 0,
            "mlt_saving_fraction": None,
            "mvt_to_mlt_size_ratio": None,
            "mvt_gzip_saving_fraction": None,
            "mlt_raw_saving_fraction": None,
            "mlt_after_gzip_saving_fraction": None,
            "mlt_plus_gzip_saving_fraction": None,
            "layer_breakdown": [],
        }

    x_values = sorted({x for x, _ in coordinates})
    y_min = min(y for _, y in coordinates)
    y_max = max(y for _, y in coordinates)
    placeholders = ",".join("?" for _ in x_values)
    params: list[object] = [map_name, zoom, y_min, y_max, *x_values]
    db_path = Path(db_path)
    from .tile_store import connect
    connection = connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT * FROM v_tile_comparison
            WHERE map_name = ? AND z = ? AND y BETWEEN ? AND ? AND x IN ({placeholders})
            """,
            params,
        ).fetchall()
        coordinate_set = set(coordinates)
        names = [c[0] for c in connection.description]
        rows = [dict(zip(names,row)) for row in rows]
        rows = [row for row in rows if (row["x"], row["y"]) in coordinate_set]

        layer_rows = connection.execute(
            f"""
            SELECT tls.layer_name, tls.geometry_type,
                   SUM(tls.feature_instances) AS feature_instances
            FROM tile_layer_stats tls
            JOIN maps m ON m.id = tls.map_id
            WHERE m.name = ? AND tls.z = ? AND tls.y BETWEEN ? AND ? AND tls.x IN ({placeholders})
            GROUP BY tls.layer_name, tls.geometry_type
            ORDER BY feature_instances DESC, tls.layer_name
            """,
            params,
        ).fetchall()
        names = [c[0] for c in connection.description]
        layer_rows = [dict(zip(names,row)) for row in layer_rows]

        mvt_bytes = sum(int(row["mvt_bytes"] or 0) for row in rows)
        mlt_bytes = sum(int(row["mlt_bytes"] or 0) for row in rows)
        mvt_raw_bytes = sum(int(row["mvt_raw_bytes"] or 0) for row in rows)
        mvt_gzip_bytes = sum(int(row["mvt_gzip_bytes"] or 0) for row in rows)
        mlt_raw_bytes = sum(int(row["mlt_raw_bytes"] or 0) for row in rows)
        mlt_gzip_bytes = sum(int(row["mlt_gzip_bytes"] or 0) for row in rows)
        feature_instances = sum(int(row["feature_instances"] or 0) for row in rows)
        return {
            "map_name": map_name,
            "zoom": zoom,
            "center_lon": center_lon,
            "center_lat": center_lat,
            "width_px": width_px,
            "height_px": height_px,
            "tile_size": tile_size,
            "viewport_tiles": len(coordinates),
            "present_tiles": len(rows),
            "feature_instances": feature_instances,
            "mvt_bytes": mvt_bytes,
            "mlt_bytes": mlt_bytes,
            "mvt_raw_bytes": mvt_raw_bytes,
            "mvt_gzip_bytes": mvt_gzip_bytes,
            "mlt_raw_bytes": mlt_raw_bytes,
            "mlt_gzip_bytes": mlt_gzip_bytes,
            "mlt_saving_fraction": (1.0 - mlt_bytes / mvt_bytes) if mvt_bytes else None,
            "mvt_to_mlt_size_ratio": (mvt_bytes / mlt_bytes) if mlt_bytes else None,
            "mvt_gzip_saving_fraction": (
                1.0 - mvt_gzip_bytes / mvt_raw_bytes
            ) if mvt_raw_bytes else None,
            "mlt_raw_saving_fraction": (
                1.0 - mlt_raw_bytes / mvt_raw_bytes
            ) if mvt_raw_bytes else None,
            "mlt_after_gzip_saving_fraction": (
                1.0 - mlt_gzip_bytes / mvt_gzip_bytes
            ) if mvt_gzip_bytes else None,
            "mlt_plus_gzip_saving_fraction": (
                1.0 - mlt_gzip_bytes / mvt_raw_bytes
            ) if mvt_raw_bytes else None,
            "layer_breakdown": layer_rows,
            "tile_coordinates": coordinates,
        }
    finally:
        connection.close()


__all__ = [
    "ArchivePair",
    "BuildReport",
    "build_working_database",
    "discover_pairs",
    "estimate_viewport",
    "find_project_root",
    "get_analysis_errors",
    "get_default_paths",
    "get_compression_buckets",
    "get_layer_analysis",
    "get_map_overview",
    "get_mlt_stream_analysis",
    "get_tile_compression_analysis",
    "get_variant_overview",
    "get_property_schema",
    "get_property_values",
    "get_semantic_types",
    "get_zoom_analysis",
    "inspect_archive",
    "iter_tile_runs",
    "list_maps",
    "read_pmtiles_header",
    "read_pmtiles_metadata",
    "tileid_to_zxy",
    "viewport_tile_coordinates",
]
