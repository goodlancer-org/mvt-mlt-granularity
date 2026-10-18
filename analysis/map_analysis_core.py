from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import shutil
import traceback
import warnings
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import brotli
import sqlite3
import mapbox_vector_tile as mvtcodec
import maplibre_tiles as mltcodec
import numpy as np
import pyogrio
from pyogrio.raw import read as ogr_read
import rasterio
import shapely
import zstandard as zstd
from pmtiles.reader import MmapSource, Reader, all_tiles
from pmtiles.tile import TileType
from pyproj import Geod

SCHEMA_VERSION = 3
ANALYZER_VERSION = "0.3.2"
SUPPORTED_MAP_EXTENSIONS = {".pmtiles", ".pbf", ".gpkg", ".gml", ".shp", ".tif", ".tiff", ".zip"}
VECTOR_EXTENSIONS = {".pbf", ".gpkg", ".gml", ".shp"}
RASTER_EXTENSIONS = {".tif", ".tiff"}
CATEGORY_FIELDS = {
    "class",
    "subclass",
    "type",
    "kind",
    "category",
    "highway",
    "building",
    "waterway",
    "landuse",
    "landcover",
    "natural",
    "amenity",
    "railway",
    "place",
    "boundary",
    "leisure",
    "surface",
    "route",
    "aeroway",
    "function",
    "functie",
    "functieplus",
    "plusfunctie",
    "objecttype",
    "object_type",
    "featuretype",
    "feature_type",
}
NAME_FIELDS = {"name", "name_en", "name:en", "label", "title"}
ID_FIELDS = {"id", "fid", "gid", "objectid", "osm_id", "osm_way_id", "osm_relation_id"}
GEOMETRY_TYPES = {
    -1: "None",
    0: "Point",
    1: "LineString",
    2: "LinearRing",
    3: "Polygon",
    4: "MultiPoint",
    5: "MultiLineString",
    6: "MultiPolygon",
    7: "GeometryCollection",
}
SEMANTIC_RULES = {
    "buildings": {
        "building", "buildings", "structure", "structures", "house", "houses",
        "pand", "gebouw", "gebouwen", "gebouwinstallatie", "overigbouwwerk",
    },
    "transportation": {
        "transportation", "transport", "road", "roads", "street", "streets", "highway",
        "rail", "railway", "track", "tracks", "path", "paths", "bridge", "bridges",
        "tunnel", "tunnels", "weg", "wegdeel", "ondersteunendwegdeel", "spoor", "spoorbaan",
        "rijbaan", "fietspad", "voetpad", "parkeervlak", "overbruggingsdeel", "tunneldeel",
    },
    "hydrography": {
        "water", "waterway", "river", "rivers", "lake", "lakes", "stream", "streams",
        "canal", "canals", "wetland", "wetlands", "ocean", "sea", "waterdeel",
        "ondersteunendwaterdeel", "sloot", "vijver",
    },
    "land_use": {
        "landuse", "land", "landcover", "agriculture", "agricultural", "irrigation", "crop",
        "crops", "forest", "forests", "vegetation", "vegetatieobject", "begroeidterreindeel",
        "onbegroeidterreindeel", "terrein",
    },
    "places": {"place", "places", "settlement", "settlements", "city", "town", "village", "locality", "plaats"},
    "points_of_interest": {
        "poi", "amenity", "amenities", "school", "hospital", "shop", "restaurant", "tourism",
    },
    "boundaries": {"boundary", "boundaries", "admin", "administrative", "border", "borders", "grens"},
    "terrain": {"terrain", "elevation", "contour", "contours", "mountain", "mountains", "hill", "hills", "peak", "peaks", "slope", "hoogte"},
    "addresses": {"address", "addresses", "housenumber", "house_number", "adres", "huisnummer"},
    "aeroway": {"aeroway", "airport", "airports", "runway", "runways", "luchthaven"},
    "infrastructure": {
        "straatmeubilair", "installatie", "kast", "mast", "paal", "put", "sensor", "bord",
        "bak", "kunstwerkdeel", "scheiding",
    },
}

SOURCE_TYPE_RULES = {
    "pand": ("buildings", "building"),
    "gebouwinstallatie": ("buildings", "building_installation"),
    "overigbouwwerk": ("buildings", "other_structure"),
    "wegdeel": ("transportation", "road_segment"),
    "ondersteunendwegdeel": ("transportation", "supporting_road_segment"),
    "spoor": ("transportation", "railway"),
    "overbruggingsdeel": ("transportation", "bridge_part"),
    "tunneldeel": ("transportation", "tunnel_part"),
    "waterdeel": ("hydrography", "water_part"),
    "ondersteunendwaterdeel": ("hydrography", "supporting_water_part"),
    "vegetatieobject": ("land_use", "vegetation_object"),
    "begroeidterreindeel": ("land_use", "vegetated_terrain"),
    "onbegroeidterreindeel": ("land_use", "unvegetated_terrain"),
    "straatmeubilair": ("infrastructure", "street_furniture"),
    "installatie": ("infrastructure", "installation"),
    "kast": ("infrastructure", "cabinet"),
    "mast": ("infrastructure", "mast"),
    "paal": ("infrastructure", "pole"),
    "put": ("infrastructure", "manhole"),
    "sensor": ("infrastructure", "sensor"),
    "bord": ("infrastructure", "sign"),
    "bak": ("infrastructure", "container"),
    "scheiding": ("infrastructure", "barrier"),
}

VALUE_TYPE_RULES = {
    "voetpad": ("transportation", "footpath"),
    "fietspad": ("transportation", "cycleway"),
    "spoorbaan": ("transportation", "railway"),
    "parkeervlak": ("transportation", "parking_area"),
    "rijbaan lokale weg": ("transportation", "local_road_carriageway"),
    "rijbaan regionale weg": ("transportation", "regional_road_carriageway"),
    "rijbaan autosnelweg": ("transportation", "motorway_carriageway"),
    "inrit": ("transportation", "driveway"),
    "uitrit": ("transportation", "driveway"),
}

GEOD = Geod(ellps="WGS84")


@dataclass
class FieldAccumulator:
    populated_count: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)
    values: Counter[str] = field(default_factory=Counter)
    value_types: dict[str, str] = field(default_factory=dict)
    cardinality_exceeded: bool = False
    description: str | None = None
    declared_values: dict[str, str | None] = field(default_factory=dict)

    def add(self, value: Any, limit: int) -> None:
        if value is None:
            return
        self.populated_count += 1
        type_name = _value_type(value)
        self.type_counts[type_name] += 1
        if self.cardinality_exceeded:
            return
        normalized = _value_text(value)
        self.values[normalized] += 1
        self.value_types[normalized] = type_name
        if len(self.values) > limit:
            self.values.clear()
            self.value_types.clear()
            self.cardinality_exceeded = True


@dataclass
class LayerAccumulator:
    layer_name: str
    description: str | None = None
    feature_count: int = 0
    vertex_count: int = 0
    features_with_id: int = 0
    min_zoom: int | None = None
    max_zoom: int | None = None
    declared_geometries: set[str] = field(default_factory=set)
    geometry_counts: Counter[str] = field(default_factory=Counter)
    geometry_vertices: Counter[str] = field(default_factory=Counter)
    fields: dict[str, FieldAccumulator] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    used_linear_fallback: bool = False

    def add_feature(
        self,
        geometry_type: str | None,
        vertices: int,
        properties: dict[str, Any],
        categorical_limit: int,
        feature_id: Any = None,
        zoom: int | None = None,
    ) -> None:
        self.feature_count += 1
        self.vertex_count += vertices
        if feature_id is not None:
            self.features_with_id += 1
        geometry_name = geometry_type or "None"
        self.geometry_counts[geometry_name] += 1
        self.geometry_vertices[geometry_name] += vertices
        if zoom is not None:
            self.min_zoom = zoom if self.min_zoom is None else min(self.min_zoom, zoom)
            self.max_zoom = zoom if self.max_zoom is None else max(self.max_zoom, zoom)
        for field_name, value in properties.items():
            accumulator = self.fields.setdefault(str(field_name), FieldAccumulator())
            accumulator.add(value, categorical_limit)


@dataclass
class MapAccumulator:
    map_name: str
    source_format: str
    file_bytes: int
    component_count: int = 0
    map_kind: str = "unknown"
    tile_encoding: str | None = None
    crs_values: set[str] = field(default_factory=set)
    min_zoom: int | None = None
    max_zoom: int | None = None
    title: str | None = None
    description: str | None = None
    attribution: str | None = None
    layers: dict[str, LayerAccumulator] = field(default_factory=dict)
    semantic_texts: list[tuple[str, str, float]] = field(default_factory=list)

    def layer(self, layer_name: str) -> LayerAccumulator:
        return self.layers.setdefault(layer_name, LayerAccumulator(layer_name=layer_name))


@dataclass
class RasterBandAccumulator:
    pixel_count: int = 0
    sum_value: float = 0.0
    sum_square: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    values: Counter[str] = field(default_factory=Counter)
    value_types: dict[str, str] = field(default_factory=dict)
    cardinality_exceeded: bool = False
    description: str | None = None
    declared_values: dict[str, str | None] = field(default_factory=dict)

    def add(self, values: np.ndarray, limit: int) -> None:
        if values.size == 0:
            return
        if np.issubdtype(values.dtype, np.floating):
            values = values[np.isfinite(values)]
            if values.size == 0:
                return
        numeric = values.astype(np.float64, copy=False)
        self.pixel_count += int(numeric.size)
        self.sum_value += float(np.sum(numeric, dtype=np.float64))
        self.sum_square += float(np.sum(numeric * numeric, dtype=np.float64))
        block_minimum = float(np.min(numeric))
        block_maximum = float(np.max(numeric))
        self.minimum = block_minimum if self.minimum is None else min(self.minimum, block_minimum)
        self.maximum = block_maximum if self.maximum is None else max(self.maximum, block_maximum)
        if self.cardinality_exceeded:
            return
        unique_values, counts = np.unique(values, return_counts=True)
        if len(self.values) + len(unique_values) > limit * 2:
            self.values.clear()
            self.value_types.clear()
            self.cardinality_exceeded = True
            return
        for value, count in zip(unique_values.tolist(), counts.tolist()):
            normalized = _value_text(value)
            self.values[normalized] += int(count)
            self.value_types[normalized] = _value_type(value)
        if len(self.values) > limit:
            self.values.clear()
            self.value_types.clear()
            self.cardinality_exceeded = True


class InsertBuffer:
    def __init__(self, connection: sqlite3.Connection, sql: str, size: int = 5000) -> None:
        self.connection = connection
        self.sql = sql
        self.size = size
        self.rows: list[tuple[Any, ...]] = []

    def add(self, row: tuple[Any, ...]) -> None:
        self.rows.append(row)
        if len(self.rows) >= self.size:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        self.connection.executemany(self.sql, self.rows)
        self.rows.clear()


def rebuild_analysis(
    map_root: str | Path,
    db_path: str | Path,
    categorical_limit: int = 128,
    arrow_batch_size: int = 65536,
    *,
    files: list[Path] | None = None,
    cache_dir: Path | None = None,
) -> dict[str, int]:
    """Rebuild the complete analytical SQLite dataset from the map source files."""
    root = Path(map_root).resolve()
    target = Path(db_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Map directory does not exist: {root}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    cache_root = cache_dir or root / ".analysis_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    map_files = files if files is not None else _discover_map_files(root)
    if not map_files:
        raise FileNotFoundError(f"No input maps under {root}")
    connection = sqlite3.connect(str(temporary))
    connection.execute("PRAGMA journal_mode = OFF")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA cache_size = -262144")
    try:
        _create_schema(connection)
        connection.execute(
            "INSERT INTO analysis_meta VALUES (?, ?, ?)",
            (SCHEMA_VERSION, ANALYZER_VERSION, datetime.now(timezone.utc).isoformat()),
        )
        for map_path in map_files:
            print(f"Profiling {map_path.name}", flush=True)
            _analyze_map(
                connection,
                map_path,
                cache_root,
                categorical_limit,
                arrow_batch_size,
            )
        connection.commit()
    finally:
        connection.close()
    os.replace(temporary, target)
    return {
        "maps": len(map_files),
        "databaseBytes": target.stat().st_size,
    }


def _analyze_map(
    connection: sqlite3.Connection,
    map_path: Path,
    cache_root: Path,
    categorical_limit: int,
    arrow_batch_size: int,
) -> None:
    """Analyze one source file as one logical map and persist only aggregate results."""
    map_name = map_path.name
    accumulator = MapAccumulator(
        map_name=map_name,
        source_format=_source_format(map_path),
        file_bytes=map_path.stat().st_size,
    )
    connection.execute("DELETE FROM _tile_metrics")
    connection.execute("DELETE FROM _tile_layer_metrics")
    try:
        components = _materialize_components(map_path, cache_root)
        accumulator.component_count = len(components)
        for component_index, component_path in enumerate(components, start=1):
            component_name = component_path.name
            suffix = component_path.suffix.lower()
            try:
                if suffix == ".pmtiles":
                    _analyze_pmtiles_component(
                        connection,
                        component_path,
                        map_name,
                        component_index,
                        component_name,
                        accumulator,
                        categorical_limit,
                    )
                elif suffix in VECTOR_EXTENSIONS:
                    _analyze_vector_component(
                        connection,
                        component_path,
                        map_name,
                        component_index,
                        component_name,
                        accumulator,
                        categorical_limit,
                        arrow_batch_size,
                    )
                elif suffix in RASTER_EXTENSIONS:
                    _analyze_raster_component(
                        connection,
                        component_path,
                        map_name,
                        component_index,
                        component_name,
                        accumulator,
                        categorical_limit,
                    )
            except Exception as error:
                _record_error(connection, map_name, component_name, "component", error, component_path)
        _write_layer_aggregates(connection, accumulator, categorical_limit)
        _write_zoom_aggregates(connection, accumulator.map_name)
        _write_map_row(connection, accumulator)
    except Exception as error:
        _record_error(connection, map_name, None, "map", error, map_path)
        _write_map_row(connection, accumulator)


def _analyze_pmtiles_component(
    connection: sqlite3.Connection,
    path: Path,
    map_name: str,
    component_index: int,
    component_name: str,
    accumulator: MapAccumulator,
    categorical_limit: int,
) -> None:
    """Extract tile, layer, geometry, property, and semantic aggregates from a PMTiles component."""
    tile_buffer = InsertBuffer(
        connection,
        "INSERT INTO _tile_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    )
    layer_buffer = InsertBuffer(
        connection,
        "INSERT INTO _tile_layer_metrics VALUES (?, ?, ?, ?, ?, ?)",
    )
    with open(path, "rb") as file_handle:
        source = MmapSource(file_handle)
        reader = Reader(source)
        header = reader.header()
        metadata = reader.metadata() or {}
        tile_type = header["tile_type"]
        compression = header["tile_compression"]
        encoding = getattr(tile_type, "name", str(tile_type))
        incoming_kind = "tiled_vector" if tile_type in {TileType.MVT, TileType.MLT} else "tiled_raster"
        accumulator.map_kind = _merge_kind(accumulator.map_kind, incoming_kind)
        accumulator.tile_encoding = encoding if accumulator.tile_encoding in {None, encoding} else "mixed"
        accumulator.min_zoom = _min_optional(accumulator.min_zoom, int(header["min_zoom"]))
        accumulator.max_zoom = _max_optional(accumulator.max_zoom, int(header["max_zoom"]))
        accumulator.title = accumulator.title or _text_or_none(metadata.get("name") or metadata.get("title"))
        accumulator.description = accumulator.description or _text_or_none(metadata.get("description"))
        accumulator.attribution = accumulator.attribution or _text_or_none(metadata.get("attribution"))
        vector_metadata = _vector_layer_metadata(metadata)
        for key, value in _string_metadata(metadata).items():
            connection.execute(
                "INSERT INTO semantic_metadata VALUES (?, ?, ?, ?, ?, ?)",
                [map_name, component_name, None, key, value, "pmtiles_metadata"],
            )
        for layer_name, layer_metadata in vector_metadata.items():
            layer = accumulator.layer(layer_name)
            layer.description = layer.description or _text_or_none(layer_metadata.get("description"))
            layer.metadata.update(_string_metadata(layer_metadata))
            for field_name, field_description in (layer_metadata.get("fields") or {}).items():
                field_accumulator = layer.fields.setdefault(str(field_name), FieldAccumulator())
                field_accumulator.description = field_accumulator.description or _metadata_value_text(field_description)
            if layer_metadata.get("minzoom") is not None:
                layer.min_zoom = _min_optional(layer.min_zoom, int(layer_metadata["minzoom"]))
            if layer_metadata.get("maxzoom") is not None:
                layer.max_zoom = _max_optional(layer.max_zoom, int(layer_metadata["maxzoom"]))
        connection.execute(
            "INSERT INTO components VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                map_name,
                component_index,
                component_name,
                "PMTiles",
                path.stat().st_size,
                encoding,
                None,
                int(header["min_zoom"]),
                int(header["max_zoom"]),
                int(header["addressed_tiles_count"]),
                int(header["tile_data_length"]),
            ],
        )
        for zxy, stored_payload in all_tiles(source):
            z, _, y = zxy
            decoded_payload = _decompress_payload(stored_payload, compression)
            tile_feature_count = 0
            tile_vertex_count = 0
            tile_layer_count = 0
            if tile_type == TileType.MVT:
                decoded_layers = mvtcodec.decode(decoded_payload)
                tile_layer_count = len(decoded_layers)
                for layer_name, decoded_layer in decoded_layers.items():
                    layer = accumulator.layer(str(layer_name))
                    features = decoded_layer.get("features", [])
                    layer_vertices = 0
                    for feature in features:
                        geometry = feature.get("geometry")
                        geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
                        vertices = _count_geojson_vertices(geometry)
                        properties = feature.get("properties") or {}
                        layer.add_feature(
                            geometry_type,
                            vertices,
                            properties,
                            categorical_limit,
                            feature.get("id"),
                            int(z),
                        )
                        layer_vertices += vertices
                    layer_buffer.add((map_name, int(z), str(layer_name), len(features), layer_vertices, 1))
                    tile_feature_count += len(features)
                    tile_vertex_count += layer_vertices
            elif tile_type == TileType.MLT:
                decoded_layers = mltcodec.decode_mlt(decoded_payload)
                tile_layer_count = len(decoded_layers)
                for decoded_layer in decoded_layers:
                    layer_name = str(decoded_layer.name)
                    layer = accumulator.layer(layer_name)
                    layer_vertices = 0
                    for feature in decoded_layer.features:
                        vertices = _count_wkb_vertices(feature.wkb)
                        properties = dict(feature.properties)
                        layer.add_feature(
                            str(feature.geometry_type),
                            vertices,
                            properties,
                            categorical_limit,
                            feature.id,
                            int(z),
                        )
                        layer_vertices += vertices
                    layer_buffer.add((map_name, int(z), layer_name, len(decoded_layer.features), layer_vertices, 1))
                    tile_feature_count += len(decoded_layer.features)
                    tile_vertex_count += layer_vertices
            tile_buffer.add(
                (
                    map_name,
                    int(z),
                    tile_layer_count,
                    tile_feature_count,
                    tile_vertex_count,
                    len(stored_payload),
                    len(decoded_payload),
                    _tile_area_km2(int(z), int(y)),
                )
            )
    tile_buffer.flush()
    layer_buffer.flush()


def _analyze_vector_component(
    connection: sqlite3.Connection,
    path: Path,
    map_name: str,
    component_index: int,
    component_name: str,
    accumulator: MapAccumulator,
    categorical_limit: int,
    arrow_batch_size: int,
) -> None:
    """Profile OGR vector data while bypassing geometry decoding when the source exceeds Shapely's model."""
    accumulator.map_kind = _merge_kind(accumulator.map_kind, "vector")
    listed_layers = pyogrio.list_layers(path)
    component_crs: set[str] = set()
    for layer_pair in listed_layers:
        layer_name = str(layer_pair[0])
        declared_geometry = None if layer_pair[1] is None else str(layer_pair[1])
        layer = accumulator.layer(layer_name)
        if declared_geometry:
            layer.declared_geometries.add(declared_geometry)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Non closed ring detected.*", category=RuntimeWarning)
            info = pyogrio.read_info(path, layer=layer_name, force_feature_count=True, force_total_bounds=False)
        info_geometry = _text_or_none(info.get("geometry_type"))
        if info_geometry:
            layer.declared_geometries.add(info_geometry)
        crs = _text_or_none(info.get("crs"))
        if crs:
            accumulator.crs_values.add(crs)
            component_crs.add(crs)
        metadata = info.get("layer_metadata") or info.get("metadata") or {}
        if isinstance(metadata, dict):
            layer.metadata.update(_string_metadata(metadata))
            layer.description = layer.description or _text_or_none(
                metadata.get("DESCRIPTION") or metadata.get("description") or metadata.get("TITLE")
            )
        source_geometry = info_geometry or declared_geometry
        try:
            if path.suffix.lower() == ".gml" or _requires_geometryless_fallback(source_geometry):
                _record_error(connection, map_name, component_name, "geometry_unavailable",
                              ValueError("Geometry-less fallback: vertex count is unknown"), path,
                              layer_name=layer_name)
                _read_vector_layer_without_geometry(
                    path, layer_name, layer, categorical_limit, arrow_batch_size, int(info.get("features") or 0)
                )
                _apply_schema_geometry_counts(layer, source_geometry)
            else:
                try:
                    _read_vector_layer_arrow(path, layer_name, layer, categorical_limit, arrow_batch_size)
                except Exception as error:
                    if not _requires_linear_fallback(error):
                        raise
                    _reset_layer_observations(layer)
                    _record_error(connection, map_name, component_name, "geometry_unavailable",
                                  error, path, layer_name=layer_name)
                    _read_vector_layer_without_geometry(
                        path, layer_name, layer, categorical_limit, arrow_batch_size, int(info.get("features") or 0)
                    )
                    _apply_schema_geometry_counts(layer, source_geometry)
        except Exception as error:
            _reset_layer_observations(layer)
            layer.feature_count = int(info.get("features") or 0)
            if source_geometry:
                _apply_schema_geometry_counts(layer, source_geometry)
            _record_error(
                connection,
                map_name,
                component_name,
                "vector_layer",
                error,
                path,
                layer_name=layer_name,
            )
        if path.suffix.lower() == ".gpkg":
            _apply_gpkg_schema_semantics(path, layer_name, layer)
        _apply_sidecar_xsd_semantics(path, layer_name, layer)
    connection.execute(
        "INSERT INTO components VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            map_name,
            component_index,
            component_name,
            _source_format(path),
            _component_size(path),
            None,
            ", ".join(sorted(component_crs)) or None,
            None,
            None,
            len(listed_layers),
            None,
        ],
    )


def _requires_linear_fallback(error: Exception) -> bool:
    text = str(error).casefold()
    markers = (
        "nonlinear geometry",
        "non-linear geometry",
        "curvilinear",
        "circularstring",
        "compoundcurve",
        "curvepolygon",
        "multicurve",
        "multisurface",
        "polyhedralsurface",
        "unsupported geometry type",
        "tin geometry",
    )
    return isinstance(error, NotImplementedError) or any(marker in text for marker in markers)


def _requires_geometryless_fallback(geometry_type: str | None) -> bool:
    """Return whether a declared geometry type should bypass Shapely decoding."""
    if not geometry_type:
        return False
    normalized = re.sub(r"[^a-z]", "", geometry_type.casefold())
    markers = (
        "circularstring",
        "compoundcurve",
        "curvepolygon",
        "multicurve",
        "multisurface",
        "polyhedralsurface",
        "triangulatedsurface",
        "triangle",
        "tin",
    )
    return any(marker in normalized for marker in markers)


def _analysis_geometry_type(source_geometry_type: str | None) -> str:
    """Map an extended OGR geometry name to the nearest Simple Features geometry class."""
    if not source_geometry_type:
        return "Unknown"
    normalized = re.sub(r"[^a-z]", "", source_geometry_type.casefold())
    if "multisurface" in normalized or "polyhedralsurface" in normalized or "triangulatedsurface" in normalized or normalized.endswith("tin"):
        return "MultiPolygon"
    if "curvepolygon" in normalized or normalized.endswith("triangle"):
        return "Polygon"
    if "multicurve" in normalized:
        return "MultiLineString"
    if "compoundcurve" in normalized or "circularstring" in normalized:
        return "LineString"
    canonical = (
        ("multipolygon", "MultiPolygon"),
        ("multilinestring", "MultiLineString"),
        ("multipoint", "MultiPoint"),
        ("polygon", "Polygon"),
        ("linestring", "LineString"),
        ("point", "Point"),
        ("geometrycollection", "GeometryCollection"),
    )
    for marker, result in canonical:
        if marker in normalized:
            return result
    return source_geometry_type


def _apply_schema_geometry_counts(layer: LayerAccumulator, source_geometry_type: str | None) -> None:
    """Record geometry counts from the layer schema when coordinates are intentionally not decoded."""
    analysis_type = _analysis_geometry_type(source_geometry_type)
    layer.geometry_counts.clear()
    layer.geometry_vertices.clear()
    layer.geometry_counts[analysis_type] = layer.feature_count
    layer.geometry_vertices[analysis_type] = None
    layer.vertex_count = None
    layer.metadata["geometry_analysis_mode"] = "schema_only"
    layer.metadata["geometry_source_type"] = source_geometry_type or "Unknown"
    layer.metadata["geometry_analysis_type"] = analysis_type


def _read_vector_layer_arrow(
    path: Path,
    layer_name: str,
    layer: LayerAccumulator,
    categorical_limit: int,
    arrow_batch_size: int,
) -> None:
    """Read a conventional vector layer through GDAL's Arrow stream."""
    with pyogrio.open_arrow(
        path,
        layer=layer_name,
        batch_size=arrow_batch_size,
        use_pyarrow=True,
        return_fids=True,
    ) as opened:
        arrow_meta, reader = opened
        # OSM and Shapefile report an empty OGR name but expose this Arrow field.
        geometry_name = arrow_meta.get("geometry_name") or "wkb_geometry"
        fid_name = arrow_meta.get("fid_column")
        for batch in reader:
            row_count = batch.num_rows
            layer.feature_count += row_count
            if fid_name and fid_name in batch.schema.names:
                fid_values = batch.column(batch.schema.get_field_index(fid_name))
                layer.features_with_id += row_count - fid_values.null_count
            if geometry_name and geometry_name in batch.schema.names:
                geometry_values = batch.column(batch.schema.get_field_index(geometry_name))
                geometries = shapely.from_wkb(geometry_values)
                _accumulate_shapely_geometries(layer, geometries)
            for field_name in arrow_meta.get("fields", []):
                field_text = str(field_name)
                if field_text not in batch.schema.names:
                    continue
                column = batch.column(batch.schema.get_field_index(field_text))
                field_accumulator = layer.fields.setdefault(field_text, FieldAccumulator())
                for value in column.to_pylist():
                    field_accumulator.add(value, categorical_limit)
                    _accumulate_embedded_semantics(layer, field_text, value, categorical_limit)


def _read_vector_layer_without_geometry(
    path: Path,
    layer_name: str,
    layer: LayerAccumulator,
    categorical_limit: int,
    batch_size: int,
    expected_feature_count: int,
) -> None:
    """Read feature attributes without materializing geometry types unsupported by Shapely."""
    offset = 0
    while True:
        kwargs = {"TAGS_FORMAT": "JSON"} if path.suffix.lower() == ".pbf" else {}
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Non closed ring detected.*", category=RuntimeWarning)
            meta, fids, _, field_data = ogr_read(
                path,
                layer=layer_name,
                read_geometry=False,
                skip_features=offset,
                max_features=batch_size,
                return_fids=True,
                **kwargs,
            )
        if fids is not None:
            row_count = len(fids)
        elif field_data:
            row_count = len(field_data[0])
        else:
            row_count = 0
        if row_count == 0:
            break
        layer.feature_count += row_count
        if fids is not None:
            layer.features_with_id += int(np.sum(np.asarray(fids) >= 0))
        for field_name, values in zip(meta.get("fields", []), field_data):
            field_text = str(field_name)
            field_accumulator = layer.fields.setdefault(field_text, FieldAccumulator())
            for value in values.tolist():
                field_accumulator.add(value, categorical_limit)
                _accumulate_embedded_semantics(layer, field_text, value, categorical_limit)
        offset += row_count
        if row_count < batch_size:
            break
    if layer.feature_count == 0 and expected_feature_count > 0:
        layer.feature_count = expected_feature_count


def _accumulate_shapely_geometries(layer: LayerAccumulator, geometries: Any) -> None:
    type_ids = np.asarray(shapely.get_type_id(geometries))
    coordinate_counts = np.asarray(shapely.get_num_coordinates(geometries))
    layer.vertex_count += int(np.sum(coordinate_counts))
    for type_id in np.unique(type_ids):
        mask = type_ids == type_id
        geometry_type = GEOMETRY_TYPES.get(int(type_id), f"Type{int(type_id)}")
        layer.geometry_counts[geometry_type] += int(np.sum(mask))
        layer.geometry_vertices[geometry_type] += int(np.sum(coordinate_counts[mask]))


def _reset_layer_observations(layer: LayerAccumulator) -> None:
    layer.feature_count = 0
    layer.vertex_count = 0
    layer.features_with_id = 0
    layer.geometry_counts.clear()
    layer.geometry_vertices.clear()
    for accumulator in layer.fields.values():
        accumulator.populated_count = 0
        accumulator.type_counts.clear()
        accumulator.values.clear()
        accumulator.value_types.clear()
        accumulator.cardinality_exceeded = False


def _accumulate_embedded_semantics(
    layer: LayerAccumulator,
    field_name: str,
    value: Any,
    categorical_limit: int,
) -> None:
    normalized = field_name.casefold()
    if normalized not in {"other_tags", "all_tags", "tags"} or value is None or value == "":
        return
    for key, item in _parse_tag_container(value).items():
        synthetic_name = f"osm:{key}"
        field_accumulator = layer.fields.setdefault(synthetic_name, FieldAccumulator())
        field_accumulator.add(item, categorical_limit)


def _parse_tag_container(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {str(key): item for key, item in parsed.items()}
    except json.JSONDecodeError:
        pass
    result = {}
    for match in re.finditer(r'"((?:\\.|[^"\\])*)"\s*=>\s*"((?:\\.|[^"\\])*)"', text):
        key = bytes(match.group(1), "utf-8").decode("unicode_escape")
        item = bytes(match.group(2), "utf-8").decode("unicode_escape")
        result[key] = item
    return result


def _apply_gpkg_schema_semantics(path: Path, layer_name: str, layer: LayerAccumulator) -> None:
    """Read GeoPackage descriptions, column metadata, and enumerated constraints directly from the package schema."""
    with closing(sqlite3.connect(str(path))) as source:
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "gpkg_contents" in tables:
            row = source.execute(
                "SELECT identifier, description FROM gpkg_contents WHERE table_name = ?",
                (layer_name,),
            ).fetchone()
            if row:
                identifier, description = row
                if identifier:
                    layer.metadata.setdefault("gpkg_identifier", str(identifier))
                if description:
                    layer.description = layer.description or str(description)
        if "gpkg_metadata" in tables and "gpkg_metadata_reference" in tables:
            rows = source.execute(
                """
                SELECT m.id, m.md_scope, m.md_standard_uri, m.mime_type, m.metadata
                FROM gpkg_metadata AS m
                JOIN gpkg_metadata_reference AS r ON r.md_file_id = m.id
                WHERE r.reference_scope = 'geopackage' OR r.table_name = ?
                ORDER BY m.id
                """,
                (layer_name,),
            ).fetchall()
            for metadata_id, scope, standard_uri, mime_type, metadata_text in rows:
                prefix = f"gpkg_metadata_{metadata_id}"
                layer.metadata.setdefault(f"{prefix}_scope", str(scope or ""))
                layer.metadata.setdefault(f"{prefix}_standard_uri", str(standard_uri or ""))
                layer.metadata.setdefault(f"{prefix}_mime_type", str(mime_type or ""))
                if metadata_text:
                    layer.metadata.setdefault(prefix, str(metadata_text))
        if "gpkg_data_columns" not in tables:
            return
        columns = source.execute(
            """
            SELECT column_name, name, title, description, constraint_name
            FROM gpkg_data_columns
            WHERE table_name = ?
            """,
            (layer_name,),
        ).fetchall()
        for column_name, name, title, description, constraint_name in columns:
            field_accumulator = layer.fields.setdefault(str(column_name), FieldAccumulator())
            field_accumulator.description = field_accumulator.description or _first_text(title, description, name)
            if constraint_name and "gpkg_data_column_constraints" in tables:
                rows = source.execute(
                    """
                    SELECT value, description
                    FROM gpkg_data_column_constraints
                    WHERE constraint_name = ? AND constraint_type = 'enum'
                    ORDER BY value
                    """,
                    (constraint_name,),
                ).fetchall()
                for value, value_description in rows:
                    field_accumulator.declared_values[str(value)] = _text_or_none(value_description)


def _apply_sidecar_xsd_semantics(path: Path, layer_name: str, layer: LayerAccumulator) -> None:
    """Collect readily available field labels and enumerations from sidecar XML Schema files."""
    schemas = list(path.parent.glob("*.xsd"))
    if not schemas:
        return
    for schema_path in schemas:
        try:
            root = ET.parse(schema_path).getroot()
        except (ET.ParseError, OSError):
            continue
        namespace = {"xs": "http://www.w3.org/2001/XMLSchema"}
        layer_token = layer_name.casefold()
        for element in root.findall(".//xs:element", namespace):
            name = element.get("name")
            if not name:
                continue
            parent_text = " ".join(filter(None, [name, element.get("type"), element.get("ref")])).casefold()
            if layer_token not in parent_text and name not in layer.fields:
                continue
            field_accumulator = layer.fields.setdefault(name, FieldAccumulator())
            annotation = element.find("./xs:annotation/xs:documentation", namespace)
            if annotation is not None and annotation.text:
                field_accumulator.description = field_accumulator.description or annotation.text.strip()
            for enum in element.findall(".//xs:enumeration", namespace):
                value = enum.get("value")
                if value is None:
                    continue
                documentation = enum.find("./xs:annotation/xs:documentation", namespace)
                field_accumulator.declared_values[value] = documentation.text.strip() if documentation is not None and documentation.text else None

def _analyze_raster_component(
    connection: sqlite3.Connection,
    path: Path,
    map_name: str,
    component_index: int,
    component_name: str,
    accumulator: MapAccumulator,
    categorical_limit: int,
) -> None:
    """Profile raster bands, metadata, value cardinality, and exact low-cardinality class counts."""
    accumulator.map_kind = _merge_kind(accumulator.map_kind, "raster")
    with rasterio.open(path) as source:
        crs = str(source.crs) if source.crs else None
        if crs:
            accumulator.crs_values.add(crs)
        connection.execute(
            "INSERT INTO components VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                map_name,
                component_index,
                component_name,
                source.driver,
                path.stat().st_size,
                None,
                crs,
                None,
                None,
                source.count,
                source.width * source.height,
            ],
        )
        dataset_tags = source.tags()
        for key, value in dataset_tags.items():
            connection.execute(
                "INSERT INTO semantic_metadata VALUES (?, ?, ?, ?, ?, ?)",
                [map_name, component_name, None, str(key), str(value), "raster_dataset_metadata"],
            )
        for band_index in range(1, source.count + 1):
            band = RasterBandAccumulator()
            for _, window in source.block_windows(band_index):
                block = source.read(band_index, window=window, masked=True)
                values = block.compressed()
                band.add(values, categorical_limit)
            mean_value = band.sum_value / band.pixel_count if band.pixel_count else None
            variance = (
                max(0.0, band.sum_square / band.pixel_count - mean_value * mean_value)
                if band.pixel_count and mean_value is not None
                else None
            )
            std_value = math.sqrt(variance) if variance is not None else None
            description = source.descriptions[band_index - 1] if source.descriptions else None
            unit = source.units[band_index - 1] if source.units else None
            band_tags = source.tags(band_index)
            for key, value in band_tags.items():
                connection.execute(
                    "INSERT INTO semantic_metadata VALUES (?, ?, ?, ?, ?, ?)",
                    [map_name, component_name, f"band:{band_index}", str(key), str(value), "raster_band_metadata"],
                )
            semantics = _infer_semantics(
                map_name,
                None,
                list(band_tags.keys()) + list(dataset_tags.keys()),
                [str(value) for value in [*dataset_tags.values(), *band_tags.values()] if value is not None],
                description,
            )
            class_mode = "categorical" if not band.cardinality_exceeded and len(band.values) <= categorical_limit else "continuous"
            connection.execute(
                "INSERT INTO raster_bands VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    map_name,
                    component_index,
                    component_name,
                    band_index,
                    source.dtypes[band_index - 1],
                    source.width,
                    source.height,
                    band.pixel_count,
                    _scalar_or_none(source.nodatavals[band_index - 1]),
                    crs,
                    abs(float(source.transform.a)),
                    abs(float(source.transform.e)),
                    band.minimum,
                    band.maximum,
                    mean_value,
                    std_value,
                    len(band.values) if not band.cardinality_exceeded else None,
                    class_mode,
                    _text_or_none(description),
                    _text_or_none(unit),
                    semantics[0],
                ],
            )
            if class_mode == "categorical" and band.pixel_count:
                rows = [
                    (
                        map_name,
                        component_index,
                        component_name,
                        band_index,
                        value,
                        band.value_types.get(value),
                        count,
                        count / band.pixel_count,
                    )
                    for value, count in band.values.most_common()
                ]
                connection.executemany("INSERT INTO raster_values VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            evidence_text = " ".join(
                value
                for value in [description, json.dumps(dataset_tags, ensure_ascii=False), json.dumps(band_tags, ensure_ascii=False)]
                if value
            )
            if evidence_text:
                accumulator.semantic_texts.append((evidence_text, "raster_metadata", 0.85))


def _write_layer_aggregates(
    connection: sqlite3.Connection,
    accumulator: MapAccumulator,
    categorical_limit: int,
) -> None:
    """Persist layer structure plus both source-native and normalized semantic evidence."""
    for layer_name, layer in sorted(accumulator.layers.items()):
        value_evidence = []
        for field_name, field_accumulator in layer.fields.items():
            normalized_field = _semantic_field_name(field_name)
            if normalized_field in CATEGORY_FIELDS and not field_accumulator.cardinality_exceeded:
                value_evidence.extend(field_accumulator.values.keys())
        semantic_category, semantic_source, semantic_confidence, semantic_evidence = _infer_semantics(
            accumulator.map_name,
            layer_name,
            list(layer.fields.keys()),
            value_evidence,
            layer.description,
        )
        source_category, source_type = _normalize_source_type(layer_name)
        if source_category is not None:
            semantic_category = source_category
            semantic_source = "source_object_type"
            semantic_confidence = 1.0
            semantic_evidence = layer_name
        connection.execute(
            "INSERT INTO layers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                accumulator.map_name,
                layer_name,
                layer.description,
                ", ".join(sorted(layer.declared_geometries)) or None,
                layer.feature_count,
                layer.features_with_id,
                layer.vertex_count,
                len(layer.fields),
                layer.min_zoom,
                layer.max_zoom,
                semantic_category,
                semantic_source,
                semantic_confidence,
                semantic_evidence,
                "encoded_feature_instances" if accumulator.map_kind == "tiled_vector" else "source_features",
                layer.used_linear_fallback,
            ],
        )
        connection.execute(
            "INSERT INTO semantic_types VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                accumulator.map_name,
                layer_name,
                layer_name,
                None,
                None,
                source_category or semantic_category,
                source_type,
                "layer_name",
                1.0 if source_category else semantic_confidence,
                layer.feature_count,
            ],
        )
        for key, value in sorted(layer.metadata.items()):
            connection.execute(
                "INSERT INTO semantic_metadata VALUES (?, ?, ?, ?, ?, ?)",
                [accumulator.map_name, None, layer_name, key, value, "layer_metadata"],
            )
        for geometry_type, feature_count in sorted(layer.geometry_counts.items()):
            connection.execute(
                "INSERT INTO geometry_types VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    accumulator.map_name,
                    layer_name,
                    ", ".join(sorted(layer.declared_geometries)) or None,
                    geometry_type,
                    feature_count,
                    layer.geometry_vertices.get(geometry_type),
                    layer.used_linear_fallback,
                ],
            )
        for field_name, field_accumulator in sorted(layer.fields.items()):
            role = _field_role(field_name, field_accumulator, categorical_limit)
            data_type = _dominant_type(field_accumulator.type_counts)
            distinct_count = None if field_accumulator.cardinality_exceeded else len(field_accumulator.values)
            connection.execute(
                "INSERT INTO layer_fields VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    accumulator.map_name,
                    layer_name,
                    field_name,
                    data_type,
                    field_accumulator.populated_count,
                    max(0, layer.feature_count - field_accumulator.populated_count),
                    distinct_count,
                    categorical_limit + 1 if field_accumulator.cardinality_exceeded else distinct_count,
                    field_accumulator.cardinality_exceeded,
                    role,
                    field_accumulator.description,
                ],
            )
            if role == "categorical" and not field_accumulator.cardinality_exceeded and field_accumulator.populated_count:
                rows = [
                    (
                        accumulator.map_name,
                        layer_name,
                        field_name,
                        value,
                        field_accumulator.value_types.get(value),
                        count,
                        count / field_accumulator.populated_count,
                    )
                    for value, count in field_accumulator.values.most_common()
                ]
                if rows:
                    connection.executemany("INSERT INTO field_values VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            if _is_semantic_field(field_name, role):
                for value, count in field_accumulator.values.most_common():
                    category, normalized_type = _normalize_semantic_value(field_name, value, semantic_category)
                    connection.execute(
                        "INSERT INTO semantic_types VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            accumulator.map_name,
                            layer_name,
                            layer_name,
                            field_name,
                            value,
                            category,
                            normalized_type,
                            "field_value",
                            1.0 if normalized_type else 0.86,
                            count,
                        ],
                    )
            for value, description in field_accumulator.declared_values.items():
                category, normalized_type = _normalize_semantic_value(field_name, value, semantic_category)
                connection.execute(
                    "INSERT INTO semantic_types VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        accumulator.map_name,
                        layer_name,
                        layer_name,
                        field_name,
                        value,
                        category,
                        normalized_type,
                        "schema_enumeration",
                        1.0,
                        field_accumulator.values.get(value) if not field_accumulator.cardinality_exceeded else None,
                    ],
                )
                if description:
                    connection.execute(
                        "INSERT INTO semantic_metadata VALUES (?, ?, ?, ?, ?, ?)",
                        [accumulator.map_name, None, layer_name, f"{field_name}:{value}", description, "schema_enumeration_description"],
                    )

def _percentile(values: np.ndarray, percentile: float) -> float | None:
    """Return a percentile for a non-empty numeric array."""
    if values.size == 0:
        return None
    return float(np.percentile(values, percentile))


def _write_zoom_aggregates(connection: sqlite3.Connection, map_name: str) -> None:
    """Reduce transient per-tile metrics into compact zoom and zoom-layer statistics."""
    tile_rows = connection.execute(
        """
        SELECT z, layerCount, featureCount, vertexCount, storedBytes, decodedBytes, tileAreaKm2
        FROM _tile_metrics
        WHERE mapName = ?
        ORDER BY z
        """,
        (map_name,),
    ).fetchall()
    tile_groups: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in tile_rows:
        tile_groups[int(row[0])].append(row)

    for zoom, rows in sorted(tile_groups.items()):
        layer_counts = np.asarray([row[1] for row in rows], dtype=np.float64)
        feature_counts = np.asarray([row[2] for row in rows], dtype=np.float64)
        vertex_counts = np.asarray([row[3] for row in rows], dtype=np.float64)
        stored_bytes = np.asarray([row[4] for row in rows], dtype=np.float64)
        decoded_bytes = np.asarray([row[5] for row in rows], dtype=np.float64)
        tile_areas = np.asarray([row[6] for row in rows], dtype=np.float64)

        feature_total = int(feature_counts.sum())
        vertex_total = int(vertex_counts.sum())
        stored_total = int(stored_bytes.sum())
        connection.execute(
            "INSERT INTO zoom_stats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                map_name,
                zoom,
                len(rows),
                feature_total,
                vertex_total,
                stored_total,
                int(decoded_bytes.sum()),
                float(tile_areas.sum()),
                float(tile_areas.mean()),
                _percentile(tile_areas, 50),
                float(feature_counts.mean()),
                _percentile(feature_counts, 50),
                _percentile(feature_counts, 90),
                _percentile(feature_counts, 95),
                _percentile(feature_counts, 99),
                float(stored_bytes.mean()),
                _percentile(stored_bytes, 50),
                _percentile(stored_bytes, 90),
                _percentile(stored_bytes, 95),
                _percentile(stored_bytes, 99),
                stored_total / feature_total if feature_total else None,
                stored_total / vertex_total if vertex_total else None,
                float(layer_counts.mean()),
            ),
        )

    layer_rows = connection.execute(
        """
        SELECT z, layerName, featureCount, vertexCount, tileAppearance
        FROM _tile_layer_metrics
        WHERE mapName = ?
        ORDER BY z, layerName
        """,
        (map_name,),
    ).fetchall()
    layer_groups: dict[tuple[int, str], list[tuple[Any, ...]]] = defaultdict(list)
    for row in layer_rows:
        layer_groups[(int(row[0]), str(row[1]))].append(row)

    for (zoom, layer_name), rows in sorted(layer_groups.items()):
        feature_counts = np.asarray([row[2] for row in rows], dtype=np.float64)
        vertex_counts = np.asarray([row[3] for row in rows], dtype=np.float64)
        tile_appearances = np.asarray([row[4] for row in rows], dtype=np.float64)
        connection.execute(
            "INSERT INTO zoom_layers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                map_name,
                zoom,
                layer_name,
                int(tile_appearances.sum()),
                int(feature_counts.sum()),
                int(vertex_counts.sum()),
                float(feature_counts.mean()),
                _percentile(feature_counts, 50),
                _percentile(feature_counts, 95),
            ),
        )


def _write_map_row(connection: sqlite3.Connection, accumulator: MapAccumulator) -> None:
    """Persist the top-level identity, storage, metadata, and semantic summary for one map."""
    layer_categories = Counter(
        row[0]
        for row in connection.execute(
            "SELECT semanticCategory FROM layers WHERE mapName = ? AND semanticCategory IS NOT NULL",
            [accumulator.map_name],
        ).fetchall()
        if row[0]
    )
    if layer_categories:
        semantic_category = ", ".join(category for category, _ in layer_categories.most_common())
        semantic_source = "layer_semantics"
        semantic_confidence = max(
            row[0]
            for row in connection.execute(
                "SELECT semanticConfidence FROM layers WHERE mapName = ? AND semanticConfidence IS NOT NULL",
                [accumulator.map_name],
            ).fetchall()
        )
    else:
        semantic_category, semantic_source, semantic_confidence, _ = _infer_semantics(
            accumulator.map_name,
            None,
            [],
            [text for text, _, _ in accumulator.semantic_texts],
            accumulator.description,
        )
    crs_text = ", ".join(sorted(accumulator.crs_values)) or None
    error_count = connection.execute(
        "SELECT COUNT(*) FROM analysis_errors WHERE mapName = ?",
        [accumulator.map_name],
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO maps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            accumulator.map_name,
            accumulator.source_format,
            accumulator.map_kind,
            accumulator.tile_encoding,
            accumulator.component_count,
            accumulator.file_bytes,
            crs_text,
            accumulator.min_zoom,
            accumulator.max_zoom,
            accumulator.title,
            accumulator.description,
            accumulator.attribution,
            semantic_category,
            semantic_source,
            semantic_confidence,
            error_count,
        ],
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE analysis_meta (
            schemaVersion INTEGER,
            analyzerVersion VARCHAR,
            generatedAt TEXT
        );
        CREATE TABLE maps (
            mapName VARCHAR,
            sourceFormat VARCHAR,
            mapKind VARCHAR,
            tileEncoding VARCHAR,
            componentCount BIGINT,
            fileBytes BIGINT,
            crs VARCHAR,
            minZoom INTEGER,
            maxZoom INTEGER,
            title VARCHAR,
            description VARCHAR,
            attribution VARCHAR,
            semanticCategory VARCHAR,
            semanticSource VARCHAR,
            semanticConfidence DOUBLE,
            errorCount BIGINT
        );
        CREATE TABLE components (
            mapName VARCHAR,
            componentIndex INTEGER,
            componentName VARCHAR,
            format VARCHAR,
            fileBytes BIGINT,
            tileEncoding VARCHAR,
            crs VARCHAR,
            minZoom INTEGER,
            maxZoom INTEGER,
            structuralCount BIGINT,
            payloadBytes BIGINT
        );
        CREATE TABLE layers (
            mapName VARCHAR,
            layerName VARCHAR,
            description VARCHAR,
            declaredGeometry VARCHAR,
            featureInstances BIGINT,
            featuresWithId BIGINT,
            vertexCount BIGINT,
            fieldCount BIGINT,
            minZoom INTEGER,
            maxZoom INTEGER,
            semanticCategory VARCHAR,
            semanticSource VARCHAR,
            semanticConfidence DOUBLE,
            semanticEvidence VARCHAR,
            countMeaning VARCHAR,
            geometryLinearized BOOLEAN
        );
        CREATE TABLE geometry_types (
            mapName VARCHAR,
            layerName VARCHAR,
            sourceGeometryType VARCHAR,
            analysisGeometryType VARCHAR,
            featureCount BIGINT,
            vertexCount BIGINT,
            linearized BOOLEAN
        );
        CREATE TABLE layer_fields (
            mapName VARCHAR,
            layerName VARCHAR,
            fieldName VARCHAR,
            dataType VARCHAR,
            populatedCount BIGINT,
            nullOrMissingCount BIGINT,
            distinctCount BIGINT,
            distinctAtLeast BIGINT,
            cardinalityExceeded BOOLEAN,
            fieldRole VARCHAR,
            description VARCHAR
        );
        CREATE TABLE field_values (
            mapName VARCHAR,
            layerName VARCHAR,
            fieldName VARCHAR,
            value VARCHAR,
            valueType VARCHAR,
            count BIGINT,
            fraction DOUBLE
        );
        CREATE TABLE semantic_types (
            mapName VARCHAR,
            layerName VARCHAR,
            sourceType VARCHAR,
            sourceField VARCHAR,
            sourceValue VARCHAR,
            normalizedCategory VARCHAR,
            normalizedType VARCHAR,
            sourceKind VARCHAR,
            confidence DOUBLE,
            featureCount BIGINT
        );
        CREATE TABLE semantic_metadata (
            mapName VARCHAR,
            componentName VARCHAR,
            layerName VARCHAR,
            key VARCHAR,
            value VARCHAR,
            sourceKind VARCHAR
        );
        CREATE TABLE zoom_stats (
            mapName VARCHAR,
            z INTEGER,
            tileCount BIGINT,
            featureInstances BIGINT,
            vertexCount BIGINT,
            storedBytes BIGINT,
            decodedBytes BIGINT,
            tileCoverageAreaKm2 DOUBLE,
            meanTileAreaKm2 DOUBLE,
            medianTileAreaKm2 DOUBLE,
            meanFeaturesPerTile DOUBLE,
            medianFeaturesPerTile DOUBLE,
            p90FeaturesPerTile DOUBLE,
            p95FeaturesPerTile DOUBLE,
            p99FeaturesPerTile DOUBLE,
            meanStoredBytesPerTile DOUBLE,
            medianStoredBytesPerTile DOUBLE,
            p90StoredBytesPerTile DOUBLE,
            p95StoredBytesPerTile DOUBLE,
            p99StoredBytesPerTile DOUBLE,
            bytesPerFeature DOUBLE,
            bytesPerVertex DOUBLE,
            meanLayersPerTile DOUBLE
        );
        CREATE TABLE zoom_layers (
            mapName VARCHAR,
            z INTEGER,
            layerName VARCHAR,
            tileAppearances BIGINT,
            featureInstances BIGINT,
            vertexCount BIGINT,
            meanFeaturesPerTile DOUBLE,
            medianFeaturesPerTile DOUBLE,
            p95FeaturesPerTile DOUBLE
        );
        CREATE TABLE raster_bands (
            mapName VARCHAR,
            componentIndex INTEGER,
            componentName VARCHAR,
            band INTEGER,
            dataType VARCHAR,
            width BIGINT,
            height BIGINT,
            validPixelCount BIGINT,
            noData DOUBLE,
            crs VARCHAR,
            resolutionX DOUBLE,
            resolutionY DOUBLE,
            minimum DOUBLE,
            maximum DOUBLE,
            mean DOUBLE,
            stddev DOUBLE,
            uniqueValueCount BIGINT,
            valueMode VARCHAR,
            description VARCHAR,
            unit VARCHAR,
            semanticCategory VARCHAR
        );
        CREATE TABLE raster_values (
            mapName VARCHAR,
            componentIndex INTEGER,
            componentName VARCHAR,
            band INTEGER,
            value VARCHAR,
            valueType VARCHAR,
            pixelCount BIGINT,
            fraction DOUBLE
        );
        CREATE TABLE analysis_errors (
            mapName VARCHAR,
            componentName VARCHAR,
            layerName VARCHAR,
            stage VARCHAR,
            errorType VARCHAR,
            error VARCHAR,
            traceback VARCHAR
        );
        CREATE INDEX idx_layers_map ON layers(mapName);
        CREATE INDEX idx_geometry_map_layer ON geometry_types(mapName, layerName);
        CREATE INDEX idx_fields_map_layer ON layer_fields(mapName, layerName);
        CREATE INDEX idx_values_map_layer ON field_values(mapName, layerName);
        CREATE INDEX idx_semantic_types_map_layer ON semantic_types(mapName, layerName);
        CREATE INDEX idx_semantic_metadata_map_layer ON semantic_metadata(mapName, layerName);
        CREATE INDEX idx_zoom_map ON zoom_stats(mapName, z);
        CREATE INDEX idx_zoom_layers_map ON zoom_layers(mapName, z, layerName);
        CREATE INDEX idx_raster_bands_map ON raster_bands(mapName);
        CREATE INDEX idx_raster_values_map ON raster_values(mapName);
        CREATE INDEX idx_errors_map ON analysis_errors(mapName);
        CREATE TEMP TABLE _tile_metrics (
            mapName VARCHAR,
            z INTEGER,
            layerCount BIGINT,
            featureCount BIGINT,
            vertexCount BIGINT,
            storedBytes BIGINT,
            decodedBytes BIGINT,
            tileAreaKm2 DOUBLE
        );
        CREATE TEMP TABLE _tile_layer_metrics (
            mapName VARCHAR,
            z INTEGER,
            layerName VARCHAR,
            featureCount BIGINT,
            vertexCount BIGINT,
            tileAppearance BIGINT
        );
        """
    )


def _discover_map_files(root: Path) -> list[Path]:
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_MAP_EXTENSIONS
        and ".analysis_cache" not in path.parts
        and "analysis" not in path.parts
    )
    names = Counter(path.name for path in files)
    duplicates = sorted(name for name, count in names.items() if count > 1)
    if duplicates:
        raise ValueError(f"Map filenames must be unique because only basenames are stored: {', '.join(duplicates)}")
    return files


def _materialize_components(map_path: Path, cache_root: Path) -> list[Path]:
    if map_path.suffix.lower() != ".zip":
        return [map_path]
    fingerprint = hashlib.sha256(
        f"{map_path.name}:{map_path.stat().st_size}:{map_path.stat().st_mtime_ns}".encode()
    ).hexdigest()[:16]
    destination = cache_root / "extracted" / f"{map_path.stem}_{fingerprint}"
    if not destination.exists():
        destination.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(map_path, destination)
    components = sorted(
        path
        for path in destination.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_MAP_EXTENSIONS - {".zip"}
    )
    return components


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    """Extract a ZIP archive while rejecting members that escape the destination directory."""
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            target = (destination / member.filename).resolve()
            if target != destination_root and destination_root not in target.parents:
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
        zip_file.extractall(destination)


def _vector_layer_metadata(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    vector_layers = metadata.get("vector_layers") or []
    if isinstance(vector_layers, str):
        try:
            vector_layers = json.loads(vector_layers)
        except json.JSONDecodeError:
            return {}
    result = {}
    if isinstance(vector_layers, list):
        for item in vector_layers:
            if isinstance(item, dict) and item.get("id"):
                result[str(item["id"])] = item
    return result


def _string_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    return {str(key): _metadata_value_text(value) for key, value in metadata.items() if value is not None}


def _metadata_value_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _text_or_none(value)
        if text:
            return text
    return None


def _semantic_field_name(field_name: str) -> str:
    normalized = field_name.casefold()
    return normalized.split(":", 1)[1] if normalized.startswith("osm:") else normalized


def _is_semantic_field(field_name: str, role: str) -> bool:
    normalized = _semantic_field_name(field_name)
    return normalized in CATEGORY_FIELDS or role == "categorical" and normalized in {"function", "functie", "objecttype", "featuretype"}


def _normalize_source_type(source_type: str) -> tuple[str | None, str | None]:
    normalized = "".join(character.casefold() for character in source_type if character.isalnum())
    if normalized in SOURCE_TYPE_RULES:
        return SOURCE_TYPE_RULES[normalized]
    category, _, _, _ = _infer_semantics("", source_type, [], [], None)
    return category, _slug(source_type) if category else None


def _normalize_semantic_value(
    field_name: str,
    value: str,
    layer_category: str | None,
) -> tuple[str | None, str | None]:
    normalized_value = " ".join(str(value).casefold().split())
    if normalized_value in VALUE_TYPE_RULES:
        return VALUE_TYPE_RULES[normalized_value]
    field = _semantic_field_name(field_name)
    category, _, _, _ = _infer_semantics("", None, [field], [normalized_value], None)
    return category or layer_category, _slug(normalized_value) if category or layer_category else None


def _slug(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", value.casefold()).strip("_")
    return normalized or value.casefold()


def _infer_semantics(
    map_name: str,
    primary_text: str | None,
    field_names: Iterable[str],
    field_values: Iterable[str],
    description: str | None = None,
) -> tuple[str | None, str | None, float | None, str | None]:
    """Infer a conservative thematic category and record the evidence that supports it."""
    candidates = [
        (primary_text, "layer_name", 0.98),
        (description, "metadata_description", 0.94),
        (" ".join(field_names), "field_name", 0.82),
        (" ".join(field_values), "field_value", 0.76),
        (map_name, "map_name", 0.62),
    ]
    best: tuple[str | None, str | None, float | None, str | None] = (None, None, None, None)
    for text, source, confidence in candidates:
        if not text:
            continue
        tokens = _semantic_tokens(str(text))
        for category, keywords in SEMANTIC_RULES.items():
            overlap = sorted(tokens & keywords)
            if overlap and (best[2] is None or confidence > best[2]):
                best = (category, source, confidence, ", ".join(overlap[:8]))
    return best


def _semantic_tokens(text: str) -> set[str]:
    normalized = "".join(character.casefold() if character.isalnum() else " " for character in text)
    return {token for token in normalized.split() if token}


def _field_role(field_name: str, accumulator: FieldAccumulator, categorical_limit: int) -> str:
    normalized = _semantic_field_name(field_name)
    if normalized in NAME_FIELDS or normalized.startswith("name:"):
        return "name"
    if normalized in ID_FIELDS or normalized.endswith("_id"):
        return "identifier"
    dominant = _dominant_type(accumulator.type_counts)
    if dominant == "bool":
        return "boolean"
    if not accumulator.cardinality_exceeded and len(accumulator.values) <= categorical_limit:
        if normalized in CATEGORY_FIELDS or len(accumulator.values) <= max(32, int(math.sqrt(max(1, accumulator.populated_count)))):
            return "categorical"
    if dominant in {"int", "float"}:
        return "continuous"
    return "attribute"


def _dominant_type(type_counts: Counter[str]) -> str | None:
    return type_counts.most_common(1)[0][0] if type_counts else None


def _value_type(value: Any) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "bool"
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return "int"
    if isinstance(value, (float, np.floating)):
        return "float"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "bytes"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _value_text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return str(value)


def _count_geojson_vertices(geometry: Any) -> int:
    if not isinstance(geometry, dict):
        return 0
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        return 1 if coordinates else 0
    if geometry_type in {"MultiPoint", "LineString"}:
        return len(coordinates or [])
    if geometry_type in {"MultiLineString", "Polygon"}:
        return sum(len(part) for part in coordinates or [])
    if geometry_type == "MultiPolygon":
        return sum(len(ring) for polygon in coordinates or [] for ring in polygon)
    if geometry_type == "GeometryCollection":
        return sum(_count_geojson_vertices(part) for part in geometry.get("geometries", []))
    return 0


def _count_wkb_vertices(wkb: bytes | None) -> int:
    if not wkb:
        return 0
    geometry = shapely.from_wkb(wkb)
    return int(shapely.get_num_coordinates(geometry))


def _decompress_payload(payload: bytes, compression: Any) -> bytes:
    name = getattr(compression, "name", str(compression)).upper()
    if name.endswith("NONE"):
        return payload
    if name.endswith("GZIP"):
        return gzip.decompress(payload)
    if name.endswith("BROTLI"):
        return brotli.decompress(payload)
    if name.endswith("ZSTD"):
        return zstd.ZstdDecompressor().decompress(payload)
    raise ValueError(f"Unsupported PMTiles compression: {compression}")


@lru_cache(maxsize=262144)
def _tile_area_km2(z: int, y: int) -> float:
    north = _tile_latitude(z, y)
    south = _tile_latitude(z, y + 1)
    longitude_width = 360.0 / (1 << z)
    area, _ = GEOD.polygon_area_perimeter(
        [0.0, longitude_width, longitude_width, 0.0],
        [south, south, north, north],
    )
    return abs(area) / 1_000_000.0


def _tile_latitude(z: int, y: int) -> float:
    n = math.pi - 2.0 * math.pi * y / (1 << z)
    return math.degrees(math.atan(math.sinh(n)))


def _source_format(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".pmtiles": "PMTiles",
        ".pbf": "OSM PBF",
        ".gpkg": "GeoPackage",
        ".gml": "GML",
        ".shp": "Shapefile",
        ".tif": "GeoTIFF",
        ".tiff": "GeoTIFF",
        ".zip": "ZIP",
    }.get(suffix, suffix.lstrip(".").upper())


def _component_size(path: Path) -> int:
    if path.suffix.lower() != ".shp":
        return path.stat().st_size
    return sum(
        candidate.stat().st_size
        for candidate in path.parent.glob(f"{path.stem}.*")
        if candidate.is_file()
    )


def _merge_kind(current: str, incoming: str) -> str:
    if current == "unknown":
        return incoming
    if current == incoming:
        return current
    if {current, incoming} <= {"vector", "tiled_vector"}:
        return "vector"
    return "mixed"


def _record_error(
    connection: sqlite3.Connection,
    map_name: str,
    component_name: str | None,
    stage: str,
    error: Exception,
    source_path: Path | None = None,
    layer_name: str | None = None,
) -> None:
    """Persist enough exception context to diagnose failures from the analytical database alone."""
    message = str(error)
    if source_path is not None and str(source_path) in message:
        message = message.replace(str(source_path), source_path.name)
    traceback_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    if source_path is not None:
        traceback_text = traceback_text.replace(str(source_path), source_path.name)
    traceback_text = re.sub(
        r'File "([^"\n]*[\\/])([^"\\/]+)"',
        r'File "\2"',
        traceback_text,
    )
    connection.execute(
        "INSERT INTO analysis_errors VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            map_name,
            component_name,
            layer_name,
            stage,
            type(error).__name__,
            message,
            traceback_text,
        ],
    )

def _min_optional(current: int | None, value: int) -> int:
    return value if current is None else min(current, value)


def _max_optional(current: int | None, value: int) -> int:
    return value if current is None else max(current, value)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _scalar_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
