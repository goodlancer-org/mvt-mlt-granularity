"""GDAL-based vector tile pipeline for the dense-tile compression experiment."""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import codecs
from contextlib import closing
from typing import Any, Callable, Dict, Iterable, Literal, Mapping

import mapbox_vector_tile
import maplibre_tiles
from pmtiles import writer
from pmtiles.reader import MmapSource, Reader, all_tiles
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from shapely import wkb

from .process_metrics import PeakMemory, _process_rss, get_output_size


ProgressCallback = Callable[[str, str], None]
DENSE_VARIANTS = (
    {"key": "standard", "detail_offset": 0, "extent": 4096},
    {"key": "dense4", "detail_offset": 1, "extent": 8192},
    {"key": "dense16", "detail_offset": 2, "extent": 16384},
)

DEFAULT_SIMPLIFICATION = 1.6
DEFAULT_SIMPLIFICATION_MAX_ZOOM = 1.0
DEFAULT_MAX_TILE_BYTES = 2147483647
DEFAULT_MAX_TILE_FEATURES = 2147483647
SAFE_MAX_TILE_BYTES = 500000
SAFE_MAX_TILE_FEATURES = 50000
ValidationMode = Literal["none", "fast", "full"]
TileLimitsMode = Literal["experimental_unlimited", "safe"]


def _emit(progress_callback: ProgressCallback | None, stage: str, message: str) -> None:
    if progress_callback is not None:
        progress_callback(stage, message)


def _check_cancel(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Conversion cancelled by user")


def _parse_bounds(bounds: str | None) -> list[str] | None:
    if not bounds:
        return None
    parts = [part.strip() for part in str(bounds).split(",")]
    return parts if len(parts) == 4 else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        next_candidate = directory / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def _format_elapsed(seconds: float) -> str:
    whole = int(max(0, seconds))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_bytes(num_bytes: int | float | None) -> str:
    if num_bytes is None:
        return "-"
    value = float(max(0.0, num_bytes))
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for candidate in units:
        unit = candidate
        if value < 1024.0 or candidate == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def _safe_file_size(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        if path.exists():
            return path.stat().st_size
    except OSError:
        return None
    return 0


def _target_groups_for_variant(
    *,
    profile_plan: Mapping[str, Any],
    analysis: Mapping[str, Any],
    detail_offset: int,
    existing_source_layers: Iterable[str],
    preflight_feature_counts: Mapping[str, int],
) -> tuple[list[dict[str, Any]], list[str]]:
    tile_layers = profile_plan.get("tile_layers") or []
    groups: list[dict[str, Any]] = []
    unmatched_global: list[str] = []
    existing_set = {str(name) for name in existing_source_layers if str(name)}

    if tile_layers:
        for idx, tile_layer in enumerate(tile_layers, start=1):
            layer_id = str(tile_layer.get("id") or f"layer_{idx}")
            zoom = tile_layer.get("zoom") or {}
            group_min = max(0, int(zoom.get("min", 0)) - int(detail_offset))
            group_max = max(0, int(zoom.get("max", 14)) - int(detail_offset))

            requested = [str(item) for item in (tile_layer.get("source_layers") or []) if str(item)]
            present = [name for name in requested if name in existing_set]
            missing = [name for name in requested if name not in existing_set]
            unmatched_global.extend(missing)
            if not present:
                continue

            feature_count = sum(int(preflight_feature_counts.get(src, 0)) for src in present)
            conf = {
                src: {
                    "target_name": layer_id,
                    "minzoom": group_min,
                    "maxzoom": group_max,
                }
                for src in present
            }
            groups.append(
                {
                    "target_layer": layer_id,
                    "source_layers": present,
                    "unmatched_source_layers": missing,
                    "feature_count": feature_count,
                    "minzoom": group_min,
                    "maxzoom": group_max,
                    "conf": conf,
                }
            )
    else:
        layer_conf = _layer_conf(profile_plan, analysis, detail_offset)
        fallback_groups: dict[str, dict[str, Any]] = {}
        for src_layer, cfg in layer_conf.items():
            src = str(src_layer)
            if src not in existing_set:
                unmatched_global.append(src)
                continue
            target = str((cfg or {}).get("target_name") or src)
            group = fallback_groups.setdefault(
                target,
                {
                    "target_layer": target,
                    "source_layers": [],
                    "unmatched_source_layers": [],
                    "feature_count": 0,
                    "minzoom": int((cfg or {}).get("minzoom", 0)),
                    "maxzoom": int((cfg or {}).get("maxzoom", 14)),
                    "conf": {},
                },
            )
            group["source_layers"].append(src)
            group["feature_count"] += int(preflight_feature_counts.get(src, 0))
            group["conf"][src] = {
                "target_name": target,
                "minzoom": int((cfg or {}).get("minzoom", group["minzoom"])),
                "maxzoom": int((cfg or {}).get("maxzoom", group["maxzoom"])),
            }
        groups = sorted(fallback_groups.values(), key=lambda item: str(item["target_layer"]))

    groups = [group for group in groups if group.get("source_layers")]
    return groups, sorted(dict.fromkeys(unmatched_global))


def _emit_heartbeat(
    *,
    label: str,
    started_monotonic: float,
    pid: int,
    temp_db_path: Path | None,
    mbtiles_path: Path | None,
    log_callback,
    output_lines: list[str],
) -> None:
    if log_callback is None:
        return
    elapsed = _format_elapsed(time.monotonic() - started_monotonic)
    rss_bytes = _process_rss(pid)
    rss_text = _format_bytes(rss_bytes) if rss_bytes is not None else "-"
    temp_size = _format_bytes(_safe_file_size(temp_db_path))
    mbtiles_size = _format_bytes(_safe_file_size(mbtiles_path))
    line = (
        f"[heartbeat] {label}: elapsed={elapsed} "
        f"rss={rss_text} temp_db={temp_size} mbtiles={mbtiles_size}"
    )
    output_lines.append(line + "\n")
    log_callback(line)


def _run_command(
    cmd: list[str],
    *,
    label: str,
    log_callback=None,
    cancel_event=None,
    heartbeat_interval_sec: int = 20,
    temp_db_path: Path | None = None,
    mbtiles_path: Path | None = None,
    stream_line_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    print(f"\n  [{label}] Running: {' '.join(cmd)}")
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        bufsize=0,
    )

    output_lines: list[str] = []
    canceled = False
    peak = PeakMemory(lambda: _process_rss(proc.pid))
    peak.start()

    def emit_stream_line(text: str) -> None:
        clean = text.rstrip("\n\r")
        if not clean:
            return
        output_lines.append(clean + "\n")
        print(f"    {clean}")
        if log_callback is not None:
            log_callback(clean)
        if stream_line_callback is not None:
            stream_line_callback(clean)

    def reader_loop() -> None:
        if proc.stdout is None:
            return
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pending = ""
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            text = decoder.decode(chunk)
            pending += text
            while True:
                cut = len(pending)
                delim = ""
                for marker in ("\r", "\n"):
                    pos = pending.find(marker)
                    if pos != -1 and pos < cut:
                        cut = pos
                        delim = marker
                if not delim:
                    break
                token = pending[:cut]
                pending = pending[cut + 1:]
                emit_stream_line(token)
        pending += decoder.decode(b"", final=True)
        if pending:
            emit_stream_line(pending)

    reader = threading.Thread(target=reader_loop, daemon=True)
    reader.start()
    next_heartbeat = start + max(1, int(heartbeat_interval_sec))

    try:
        while True:
            try:
                return_code = proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if log_callback is not None and now >= next_heartbeat:
                    _emit_heartbeat(
                        label=label,
                        started_monotonic=start,
                        pid=proc.pid,
                        temp_db_path=temp_db_path,
                        mbtiles_path=mbtiles_path,
                        log_callback=log_callback,
                        output_lines=output_lines,
                    )
                    next_heartbeat = now + max(1, int(heartbeat_interval_sec))
                if cancel_event is not None and cancel_event.is_set():
                    canceled = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    output_lines.append("\nERROR: conversion cancelled by user.\n")
                    break
    finally:
        return_code = proc.wait()
        reader.join(timeout=2)
        if proc.stdout is not None:
            proc.stdout.close()

    elapsed = time.monotonic() - start
    peak_mb = peak.stop()
    return {
        "exit_code": 130 if canceled else return_code,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "time_seconds": round(elapsed, 2),
        "time_ms": round(elapsed * 1000),
        "peak_memory_mb": peak_mb,
        "combined_output": "".join(output_lines).strip(),
        "canceled": canceled,
    }


def _ogrinfo_preflight(
    *,
    source_path: Path,
    progress_callback: ProgressCallback | None,
    log_progress: Callable[[str, str], None] | None,
    cancel_event=None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    _emit(progress_callback, "gpkg_preflight", f"Preflight ogrinfo: {source_path.name}")
    preflight = _run_command(
        ["ogrinfo", "-ro", "-json", str(source_path)],
        label="ogrinfo preflight",
        log_callback=(lambda line: log_progress("ogrinfo", line)) if log_progress else None,
        cancel_event=cancel_event,
        heartbeat_interval_sec=20,
    )
    if preflight.get("canceled"):
        raise RuntimeError("Conversion cancelled by user")
    if preflight.get("exit_code") != 0:
        tail = (preflight.get("combined_output") or "")[-1500:]
        raise RuntimeError(f"ogrinfo preflight failed (exit {preflight.get('exit_code')}):\n{tail}")

    raw = preflight.get("combined_output") or ""
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError as exc:
        tail = raw[-1500:]
        raise RuntimeError(f"ogrinfo preflight returned non-JSON output: {exc}\n{tail}") from exc

    driver = str(
        meta.get("driverShortName")
        or meta.get("driver")
        or ((meta.get("driver") or {}).get("shortName") if isinstance(meta.get("driver"), dict) else "")
        or "unknown"
    )
    layer_rows = []
    for layer in (meta.get("layers") or []):
        if not isinstance(layer, dict):
            continue
        name = str(layer.get("name") or "").strip()
        if not name:
            continue
        count = layer.get("featureCount")
        if count is None:
            count = layer.get("feature_count")
        if count is None:
            count = layer.get("features")
        try:
            feature_count = max(0, int(count)) if count is not None and int(count) >= 0 else None
        except (TypeError, ValueError):
            feature_count = None
        layer_rows.append({"name": name, "feature_count": feature_count})

    layers = [row["name"] for row in layer_rows]

    _emit(progress_callback, "gpkg_preflight", f"ogrinfo driver: {driver}")
    _emit(progress_callback, "gpkg_preflight", f"ogrinfo layers: {len(layers)}")
    if layers:
        for index in range(0, len(layers), 20):
            chunk = layers[index:index + 20]
            _emit(progress_callback, "gpkg_preflight", f"ogrinfo layer names [{index + 1}-{index + len(chunk)}]: {', '.join(chunk)}")

    if str(driver).strip().upper() != "GPKG":
        raise RuntimeError(
            f"Stage B requires a normalized GeoPackage input, got driver '{driver}' for {source_path}."
        )

    # Enforce the Stage-A/Stage-B contract cheaply from GeoPackage metadata.
    with closing(sqlite3.connect(source_path)) as conn:
        geometry_rows = conn.execute(
            "SELECT table_name, srs_id, z, m FROM gpkg_geometry_columns"
        ).fetchall()
    wrong_crs = [f"{table}:{srs_id}" for table, srs_id, _z, _m in geometry_rows if int(srs_id) != 3857]
    non_xy = [f"{table}:z={z},m={m}" for table, _srs_id, z, m in geometry_rows if int(z) != 0 or int(m) != 0]
    if wrong_crs:
        raise RuntimeError("Stage B requires normalized EPSG:3857 layers; got " + ", ".join(wrong_crs[:20]))
    if non_xy:
        raise RuntimeError("Stage B requires XY-only normalized layers; got " + ", ".join(non_xy[:20]))

    if not layers:
        raise RuntimeError(
            "ogrinfo preflight found 0 layers in source; aborting before ogr2ogr. "
            "Verify source content/driver and try again."
        )

    total_features = sum(int(row.get("feature_count") or 0) for row in layer_rows if row.get("feature_count") is not None)
    unknown_features = sum(1 for row in layer_rows if row.get("feature_count") is None)
    suffix = f", unknown layer counts: {unknown_features}" if unknown_features else ""
    _emit(progress_callback, "gpkg_preflight", f"ogrinfo total known features: {total_features}{suffix}")

    return {
        "driver": driver,
        "layers": layers,
        "layers_with_counts": layer_rows,
        "total_features": total_features,
        "raw": raw,
        "timings": {
            "gpkg_preflight": round(time.perf_counter() - started, 3),
        },
    }


def _source_layers_for_plan(profile_plan: Mapping[str, Any], analysis: Mapping[str, Any]) -> list[str]:
    available = [
        str((layer or {}).get("name") or "").strip()
        for layer in (analysis or {}).get("layers", [])
        if isinstance(layer, dict) and str((layer or {}).get("name") or "").strip()
    ]
    if available:
        return available

    planned = []
    for layer in profile_plan.get("tile_layers") or []:
        planned.extend(str(item) for item in (layer.get("source_layers") or []) if item)
    return sorted(set(planned))


def _layer_conf(profile_plan: Mapping[str, Any], analysis: Mapping[str, Any], detail_offset: int) -> dict[str, Any]:
    """Build GDAL PMTiles/MVT CONF, preserving profile layer grouping where possible."""
    conf: dict[str, Any] = {}
    planned_layers = profile_plan.get("tile_layers") or []
    if planned_layers:
        for tile_layer in planned_layers:
            target = str(tile_layer.get("id") or "layer")
            zoom = tile_layer.get("zoom") or {}
            minzoom = max(0, int(zoom.get("min", 0)) - detail_offset)
            maxzoom = max(0, int(zoom.get("max", 14)) - detail_offset)
            for source_layer in tile_layer.get("source_layers") or [target]:
                conf[str(source_layer)] = {
                    "target_name": target,
                    "minzoom": minzoom,
                    "maxzoom": maxzoom,
                }
        return conf

    for source_layer in _source_layers_for_plan(profile_plan, analysis):
        conf[source_layer] = {"target_name": source_layer}
    return conf


def _gdal_mvt_command(
    *,
    source_path: Path,
    output_mbtiles: Path,
    min_zoom: int,
    max_zoom: int,
    bounds: str | None,
    variant: Mapping[str, Any],
    source_layers: list[str],
    layer_conf: Mapping[str, Any],
    simplification: float,
    simplification_max_zoom: float,
    max_size: int,
    max_features: int,
    temporary_db: Path | None,
) -> list[str]:
    """Build the Stage-B tiling command.

    The normalized GPKG is already cropped, XY-only and EPSG:3857, so Stage B
    deliberately does no spatial filtering and no reprojection. Tiles are first
    written by the MVT driver into MBTiles because that driver supports BOUNDS
    and TEMPORARY_DB; the resulting ready-made MVT tiles are then directly
    repacked into PMTiles.
    """
    detail_offset = int(variant["detail_offset"])
    extent = int(variant["extent"])
    buffer = max(0, round(80 * extent / 4096))
    conf = json.dumps(dict(layer_conf or {}), separators=(",", ":"))
    layer_minzooms = [
        int((cfg or {}).get("minzoom", min_zoom))
        for cfg in (layer_conf or {}).values()
        if isinstance(cfg, Mapping)
    ]
    layer_maxzooms = [
        int((cfg or {}).get("maxzoom", max_zoom))
        for cfg in (layer_conf or {}).values()
        if isinstance(cfg, Mapping)
    ]
    effective_min_zoom = min([int(min_zoom), *layer_minzooms]) if layer_minzooms else int(min_zoom)
    effective_max_zoom = max([int(min_zoom), *layer_maxzooms]) if layer_maxzooms else max(int(min_zoom), int(max_zoom) - detail_offset)

    cmd = [
        "ogr2ogr",
        "--config", "OGR_GPKG_NUM_THREADS", "4",
        "-f", "MVT",
        str(output_mbtiles),
        str(source_path),
        *[str(layer) for layer in source_layers],
        "-dsco", "FORMAT=MBTILES",
        "-dsco", f"MINZOOM={effective_min_zoom}",
        "-dsco", f"MAXZOOM={effective_max_zoom}",
        "-dsco", f"EXTENT={extent}",
        "-dsco", f"BUFFER={buffer}",
        "-dsco", f"SIMPLIFICATION={float(simplification)}",
        "-dsco", f"SIMPLIFICATION_MAX_ZOOM={float(simplification_max_zoom)}",
        "-dsco", f"MAX_SIZE={int(max_size)}",
        "-dsco", f"MAX_FEATURES={int(max_features)}",
        "-dsco", f"CONF={conf}",
    ]

    parsed_bounds = _parse_bounds(bounds)
    if parsed_bounds:
        # Metadata/output bounds only. The actual crop happened once in Stage A.
        cmd.extend(["-dsco", f"BOUNDS={','.join(parsed_bounds)}"])

    if temporary_db is not None:
        cmd.extend(["-dsco", f"TEMPORARY_DB={temporary_db}"])

    return cmd


def _pmtiles_direct_translation_command(input_mbtiles: Path, output_pmtiles: Path) -> list[str]:
    """Repack existing MVT tiles from MBTiles into PMTiles without re-tiling."""
    # GDAL documents this exact no-extra-options form as its direct translation
    # path; the .pmtiles suffix selects the PMTiles driver.
    return ["ogr2ogr", str(output_pmtiles), str(input_mbtiles)]


def _combine_command_results(first: Mapping[str, Any], second: Mapping[str, Any]) -> Dict[str, Any]:
    """Combine tile generation + PMTiles packing into one conversion result."""
    first_seconds = float(first.get("time_seconds") or 0.0)
    second_seconds = float(second.get("time_seconds") or 0.0)
    first_peak = first.get("peak_memory_mb")
    second_peak = second.get("peak_memory_mb")
    peaks = [float(v) for v in (first_peak, second_peak) if v is not None]
    return {
        "exit_code": int(second.get("exit_code") or first.get("exit_code") or 0),
        "started_at": first.get("started_at"),
        "finished_at": second.get("finished_at") or first.get("finished_at"),
        "time_seconds": round(first_seconds + second_seconds, 2),
        "time_ms": round((first_seconds + second_seconds) * 1000),
        "peak_memory_mb": max(peaks) if peaks else None,
        "combined_output": "\n".join(
            part for part in (str(first.get("combined_output") or ""), str(second.get("combined_output") or "")) if part
        ),
        "canceled": bool(first.get("canceled") or second.get("canceled")),
    }


def _read_pmtiles(path: Path):
    handle = path.open("rb")
    source = MmapSource(handle)
    return handle, source, Reader(source)


def _maybe_decompress(tile: bytes, compression: Compression) -> bytes:
    if compression == Compression.GZIP:
        return gzip.decompress(tile)
    return tile


def _maybe_compress(tile: bytes, compression: Compression) -> bytes:
    if compression == Compression.GZIP:
        return gzip.compress(tile, compresslevel=6)
    return tile


def _resolve_tile_limits(
    *,
    tile_limits_mode: TileLimitsMode,
    max_size: int,
    max_features: int,
) -> tuple[int, int]:
    if tile_limits_mode == "safe":
        resolved_size = int(max_size)
        resolved_features = int(max_features)
        if resolved_size >= DEFAULT_MAX_TILE_BYTES:
            resolved_size = SAFE_MAX_TILE_BYTES
        if resolved_features >= DEFAULT_MAX_TILE_FEATURES:
            resolved_features = SAFE_MAX_TILE_FEATURES
        return max(1, resolved_size), max(1, resolved_features)
    return max(1, int(max_size)), max(1, int(max_features))


def _scan_mvt_archive(path: Path, *, expected_extent: int) -> Dict[str, Any]:
    """One-pass MVT scan: extent validation and layer statistics."""
    handle, source, reader = _read_pmtiles(path)
    started = time.perf_counter()
    extent_mismatches: list[str] = []
    try:
        header = reader.header()
        compression = header.get("tile_compression", Compression.UNKNOWN)
        layers: dict[str, dict[str, Any]] = {}
        tile_count = 0
        feature_count = 0
        vertex_count = 0
        for zxy, payload in all_tiles(source):
            tile_count += 1
            decoded = mapbox_vector_tile.decode(
                _maybe_decompress(payload, compression),
                default_options={"y_coord_down": True},
            )
            for layer_name, layer in decoded.items():
                if not isinstance(layer, dict):
                    continue
                extent_value = layer.get("extent")
                try:
                    parsed_extent = int(extent_value) if extent_value is not None else None
                except (TypeError, ValueError):
                    parsed_extent = None
                if parsed_extent != int(expected_extent) and len(extent_mismatches) < 20:
                    shown = "missing" if parsed_extent is None else str(parsed_extent)
                    extent_mismatches.append(f"{zxy}:{layer_name}:{shown}")

                bucket = layers.setdefault(str(layer_name), {
                    "tile_count": 0,
                    "feature_count": 0,
                    "size_bytes": 0,
                    "attribute_keys": 0,
                    "attribute_values": 0,
                    "vertex_count": 0,
                })
                bucket["tile_count"] += 1
                for feature in layer.get("features") or []:
                    props = feature.get("properties") or {}
                    geom = feature.get("geometry") or {}
                    n_vertices = _vertex_count(geom.get("coordinates"))
                    bucket["feature_count"] += 1
                    bucket["attribute_keys"] += len(props)
                    bucket["attribute_values"] += len(props)
                    bucket["vertex_count"] += n_vertices
                    feature_count += 1
                    vertex_count += n_vertices

        return {
            "tile_count": tile_count,
            "feature_count": feature_count,
            "vertex_count": vertex_count,
            "layers": layers,
            "extent_validation": {
                "checked_tiles": tile_count,
                "expected_extent": int(expected_extent),
                "passed": not extent_mismatches,
                "mismatch_count": len(extent_mismatches),
                "mismatches": extent_mismatches,
            },
            "time_seconds": round(time.perf_counter() - started, 3),
        }
    finally:
        handle.close()


def transcode_mvt_pmtiles_to_mlt(
    mvt_path: Path,
    mlt_path: Path,
    *,
    validation_mode: ValidationMode = "fast",
) -> Dict[str, Any]:
    """Transcode a GDAL-generated MVT PMTiles archive into MLT PMTiles tile-by-tile."""
    mvt_path = Path(mvt_path)
    mlt_path = Path(mlt_path)
    in_handle, source, reader = _read_pmtiles(mvt_path)
    validation_seconds = 0.0
    mismatches: list[str] = []
    compared_tiles = 0
    try:
        header = dict(reader.header())
        metadata = reader.metadata() or {}
        source_compression = header.get("tile_compression", Compression.UNKNOWN)
        target_compression = Compression.GZIP
        output_header = {
            **header,
            "tile_type": TileType.MLT,
            "tile_compression": target_compression,
            "internal_compression": Compression.GZIP,
            "clustered": True,
        }

        tile_count = 0
        min_tileid = None
        max_tileid = None
        with mlt_path.open("wb") as out_handle:
            archive = writer.Writer(out_handle)
            for (z, x, y), payload in all_tiles(source):
                raw_mvt = _maybe_decompress(payload, source_compression)
                raw_mlt = bytes(maplibre_tiles.encode_mvt(raw_mvt))
                tile_id = zxy_to_tileid(z, x, y)
                min_tileid = tile_id if min_tileid is None else min(min_tileid, tile_id)
                max_tileid = tile_id if max_tileid is None else max(max_tileid, tile_id)

                if validation_mode == "full":
                    validate_started = time.perf_counter()
                    compared_tiles += 1
                    if _normal_mvt_tile(raw_mvt) != _normal_mlt_tile(raw_mlt):
                        mismatches.append(f"{(z, x, y)}: decoded content differs")
                    validation_seconds += time.perf_counter() - validate_started

                archive.write_tile(tile_id, _maybe_compress(raw_mlt, target_compression))
                tile_count += 1
            archive.finalize(output_header, metadata)
        return {
            "tile_count": tile_count,
            "validation": {
                "mode": validation_mode,
                "lightweight": {
                    "min_tileid": min_tileid,
                    "max_tileid": max_tileid,
                    "tile_count": tile_count,
                },
                "full": {
                    "checked_tiles": compared_tiles,
                    "passed": not mismatches,
                    "mismatch_count": len(mismatches),
                    "mismatches": mismatches[:20],
                }
                if validation_mode == "full"
                else None,
                "validation_seconds": round(validation_seconds, 3),
            },
        }
    finally:
        in_handle.close()


def _coords(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if isinstance(value, (list, tuple)):
        return tuple(_coords(item) for item in value)
    return value


def _vertex_count(value: Any) -> int:
    if not isinstance(value, (list, tuple)):
        return 0
    if value and all(isinstance(item, (int, float)) for item in value[:2]):
        return 1
    return sum(_vertex_count(item) for item in value)


def _wkb_coords(blob: bytes) -> Any:
    geom = wkb.loads(blob)
    return _coords(geom.__geo_interface__.get("coordinates"))


def _normal_mvt_tile(raw_mvt: bytes) -> dict[str, list[tuple[Any, Any, int]]]:
    decoded = mapbox_vector_tile.decode(raw_mvt, default_options={"y_coord_down": True})
    out: dict[str, list[tuple[Any, Any, int]]] = {}
    for layer_name, layer in decoded.items():
        features = []
        for feature in layer.get("features") or []:
            geom = feature.get("geometry")
            props = tuple(sorted((str(k), str(v)) for k, v in (feature.get("properties") or {}).items()))
            features.append((_coords(geom.get("coordinates") if isinstance(geom, dict) else geom), props, int(feature.get("id") or 0)))
        out[str(layer_name)] = sorted(features, key=repr)
    return out


def _normal_mlt_tile(raw_mlt: bytes) -> dict[str, list[tuple[Any, Any, int]]]:
    out: dict[str, list[tuple[Any, Any, int]]] = {}
    for layer in maplibre_tiles.decode_mlt(raw_mlt):
        features = []
        for feature in layer.features:
            props = tuple(sorted((str(k), str(v)) for k, v in (feature.properties or {}).items()))
            features.append((_wkb_coords(feature.wkb), props, int(feature.id or 0)))
        out[str(layer.name)] = sorted(features, key=repr)
    return out


def _conversion_entry(
    *,
    key: str,
    path: Path,
    run_result: Mapping[str, Any],
    summary: Mapping[str, Any],
    log_file: str,
    extent: int,
    detail_offset: int,
    validation: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "filename": path.name,
        "size_bytes": get_output_size(path),
        "archive_sha256": _sha256(path) if path.exists() else "",
        "tile_count": int(summary.get("tile_count") or 0),
        "feature_count": int(summary.get("feature_count") or 0),
        "vertex_count": int(summary.get("vertex_count") or 0),
        "started_at": run_result.get("started_at"),
        "finished_at": run_result.get("finished_at"),
        "time_seconds": run_result.get("time_seconds"),
        "time_ms": run_result.get("time_ms"),
        "peak_memory_mb": run_result.get("peak_memory_mb"),
        "exit_code": run_result.get("exit_code", 1),
        "failed_step": None if run_result.get("exit_code") == 0 else key,
        "layers": summary.get("layers") or {},
        "log_file": log_file,
        "error_message": None if run_result.get("exit_code") == 0 else (run_result.get("combined_output") or "")[-8000:],
        "extent": extent,
        "detail_offset": detail_offset,
        "validation": dict(validation or {}),
    }


def run_gdal_dense_pipeline(
    *,
    name: str,
    source_path: str | Path,
    output_dir: str | Path,
    logs_dir: str | Path,
    profile_plan: Mapping[str, Any],
    analysis: Mapping[str, Any],
    min_zoom: int,
    max_zoom: int,
    bounds: str | None,
    tmp_dir: str | None = None,
    variants: Iterable[Mapping[str, Any]] | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_event=None,
    log_progress: Callable[[str, str], None] | None = None,
    simplification: float = DEFAULT_SIMPLIFICATION,
    simplification_max_zoom: float = DEFAULT_SIMPLIFICATION_MAX_ZOOM,
    max_size: int = DEFAULT_MAX_TILE_BYTES,
    max_features: int = DEFAULT_MAX_TILE_FEATURES,
    validation_mode: ValidationMode = "fast",
    tile_limits_mode: TileLimitsMode = "experimental_unlimited",
) -> Dict[str, Dict[str, Any]]:
    """Generate Standard, Dense-4 and Dense-16 MVT with GDAL, then transcode each to MLT."""
    source_path = Path(source_path)
    if source_path.suffix.lower() != ".gpkg":
        raise RuntimeError(
            f"Stage B input must be a normalized GPKG, got {source_path.name}. "
            "Run source normalization first."
        )
    output_dir = Path(output_dir)
    logs_dir = Path(logs_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    preflight = _ogrinfo_preflight(
        source_path=source_path,
        progress_callback=progress_callback,
        log_progress=log_progress,
        cancel_event=cancel_event,
    )
    preflight_log = logs_dir / f"{name}_ogrinfo_preflight.log"
    preflight_log.write_text(preflight.get("raw") or "", encoding="utf-8")

    preflight_layers = preflight.get("layers_with_counts") or []
    preflight_feature_counts = {
        str(item.get("name") or ""): int(item.get("feature_count") or 0)
        for item in preflight_layers
        if str(item.get("name") or "")
    }
    preflight_order = [
        str(item.get("name") or "")
        for item in preflight_layers
        if str(item.get("name") or "")
    ]
    resolved_max_size, resolved_max_features = _resolve_tile_limits(
        tile_limits_mode=tile_limits_mode,
        max_size=int(max_size),
        max_features=int(max_features),
    )
    _emit(
        progress_callback,
        "convert",
        (
            f"[tile-limits] mode={tile_limits_mode} "
            f"MAX_SIZE={resolved_max_size} MAX_FEATURES={resolved_max_features}"
        ),
    )
    _emit(progress_callback, "convert", f"[validation-mode] mode={validation_mode}")
    _emit(
        progress_callback,
        "convert",
        "[stage-b-input] canonical GPKG: cropped in Stage A, XY/EPSG:3857; no spatial filter or reprojection",
    )
    _emit(progress_callback, "convert", "[stage-b-writer] GPKG -> MVT/MBTiles -> PMTiles direct translation")

    conversions: Dict[str, Dict[str, Any]] = {}
    for variant in (list(variants or []) or list(DENSE_VARIANTS)):
        _check_cancel(cancel_event)
        variant_key = str(variant["key"])
        extent = int(variant["extent"])
        detail_offset = int(variant["detail_offset"])
        mvt_key = f"{variant_key}_mvt"
        mlt_key = f"{variant_key}_mlt"
        effective_max_zoom = max(int(min_zoom), int(max_zoom) - detail_offset)
        mvt_path = _unique_path(output_dir, f"{name}_{variant_key}_mvt.pmtiles")
        mlt_path = _unique_path(output_dir, f"{name}_{variant_key}_mlt.pmtiles")

        target_groups, missing_from_source = _target_groups_for_variant(
            profile_plan=profile_plan,
            analysis=analysis,
            detail_offset=detail_offset,
            existing_source_layers=preflight_order,
            preflight_feature_counts=preflight_feature_counts,
        )
        if missing_from_source:
            for index in range(0, len(missing_from_source), 15):
                chunk = missing_from_source[index:index + 15]
                _emit(
                    progress_callback,
                    "convert",
                    f"profile/source mismatch: source layer(s) from profile not found in datasource: {', '.join(chunk)}",
                )
        if not target_groups:
            raise RuntimeError(
                "No target layer groups to convert after profile/source intersection. "
                "Check source layer names in profile against ogrinfo output."
            )

        total_features = sum(int(group.get("feature_count") or 0) for group in target_groups)
        combined_layer_conf: dict[str, Any] = {}
        source_layers: list[str] = []
        expected_target_layers: list[str] = []
        for group in target_groups:
            expected_target_layers.append(str(group.get("target_layer") or "layer"))
            for source_layer in group.get("source_layers") or []:
                source_name = str(source_layer)
                if source_name and source_name not in source_layers:
                    source_layers.append(source_name)
            for source_name, conf in (group.get("conf") or {}).items():
                combined_layer_conf[str(source_name)] = dict(conf or {})

        _emit(
            progress_callback,
            "convert",
            (
                f"[stage-b-plan] variant={variant_key} source_layers={len(source_layers)} "
                f"target_layers={len(set(expected_target_layers))} total_features={total_features}"
            ),
        )

        _emit(progress_callback, "convert", f"Starting GDAL {variant_key} MVT (extent {extent})")
        gdal_log = f"{name}_{mvt_key}.gdal.log"

        stage_timings = {
            "gpkg_preflight": float(((preflight.get("timings") or {}).get("gpkg_preflight") or 0.0)),
            "mvt_generation": 0.0,
            "pmtiles_pack": 0.0,
            "mvt_scan": 0.0,
            "mvt_to_mlt": 0.0,
            "mlt_validation": 0.0,
            "total_postprocessing": 0.0,
        }

        layer_run_config = {
            "variant": variant_key,
            "extent": extent,
            "detail_offset": detail_offset,
            "min_zoom": int(min_zoom),
            "max_zoom": int(effective_max_zoom),
            "simplification": float(simplification),
            "simplification_max_zoom": float(simplification_max_zoom),
            "bounds": str(bounds or ""),
            "layer_count": len(target_groups),
            "layers": [
                {
                    "target_layer": str(group.get("target_layer") or "layer"),
                    "source_layers": list(group.get("source_layers") or []),
                    "source_layer_count": len(group.get("source_layers") or []),
                    "layer_minzoom": int(group.get("minzoom", min_zoom)),
                    "layer_maxzoom": int(group.get("maxzoom", max_zoom)),
                    "feature_count": int(group.get("feature_count") or 0),
                }
                for group in target_groups
            ],
        }
        _emit(progress_callback, "convert", f"[layer-config] {json.dumps(layer_run_config, ensure_ascii=True)}")

        work_dir = Path(tmp_dir) if tmp_dir else output_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        mbtiles_path = work_dir / f".{mvt_path.stem}.work.mbtiles"
        temp_db_path = work_dir / f".{mvt_path.stem}.tilegen.sqlite"
        mbtiles_path.unlink(missing_ok=True)
        temp_db_path.unlink(missing_ok=True)

        gdal_cmd = _gdal_mvt_command(
            source_path=source_path,
            output_mbtiles=mbtiles_path,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            bounds=bounds,
            variant=variant,
            source_layers=source_layers,
            layer_conf=combined_layer_conf,
            simplification=simplification,
            simplification_max_zoom=simplification_max_zoom,
            max_size=resolved_max_size,
            max_features=resolved_max_features,
            temporary_db=temp_db_path,
        )

        tile_result = _run_command(
            gdal_cmd,
            label=f"GDAL {variant_key} MVT/MBTiles",
            log_callback=(lambda line, label=f"GDAL {variant_key}": log_progress(label, line)) if log_progress else None,
            cancel_event=cancel_event,
            heartbeat_interval_sec=20,
            temp_db_path=temp_db_path,
            mbtiles_path=mbtiles_path,
        )
        stage_timings["mvt_generation"] = float(tile_result.get("time_seconds") or 0.0)

        if tile_result.get("canceled"):
            raise RuntimeError("Conversion cancelled by user")
        if tile_result["exit_code"] != 0:
            (logs_dir / gdal_log).write_text(tile_result.get("combined_output") or "", encoding="utf-8")
            conversions[mvt_key] = _conversion_entry(
                key=mvt_key, path=mvt_path, run_result=tile_result, summary={},
                log_file=gdal_log, extent=extent, detail_offset=detail_offset,
            )
            continue

        _emit(progress_callback, "convert", f"Packing {variant_key} MVT MBTiles into PMTiles")
        pack_result = _run_command(
            _pmtiles_direct_translation_command(mbtiles_path, mvt_path),
            label=f"GDAL {variant_key} PMTiles pack",
            log_callback=(lambda line, label=f"GDAL {variant_key} pack": log_progress(label, line)) if log_progress else None,
            cancel_event=cancel_event,
            heartbeat_interval_sec=20,
            mbtiles_path=mvt_path,
        )
        stage_timings["pmtiles_pack"] = float(pack_result.get("time_seconds") or 0.0)
        gdal_result = _combine_command_results(tile_result, pack_result)
        (logs_dir / gdal_log).write_text(gdal_result.get("combined_output") or "", encoding="utf-8")

        if gdal_result.get("canceled"):
            raise RuntimeError("Conversion cancelled by user")
        if gdal_result["exit_code"] != 0:
            conversions[mvt_key] = _conversion_entry(
                key=mvt_key, path=mvt_path, run_result=gdal_result, summary={},
                log_file=gdal_log, extent=extent, detail_offset=detail_offset,
            )
            continue

        # The final PMTiles now contains the ready-made MVT payloads. Remove the
        # working databases before the scan/transcode phase.
        mbtiles_path.unlink(missing_ok=True)
        temp_db_path.unlink(missing_ok=True)

        scan_started = time.perf_counter()
        mvt_scan = _scan_mvt_archive(mvt_path, expected_extent=extent)
        stage_timings["mvt_scan"] = round(time.perf_counter() - scan_started, 3)
        stage_timings["total_postprocessing"] = round(stage_timings["mvt_scan"], 3)
        mvt_summary = {
            "tile_count": int(mvt_scan.get("tile_count") or 0),
            "feature_count": int(mvt_scan.get("feature_count") or 0),
            "vertex_count": int(mvt_scan.get("vertex_count") or 0),
            "layers": mvt_scan.get("layers") or {},
        }
        extent_validation = dict(mvt_scan.get("extent_validation") or {})
        if not extent_validation.get("passed", False):
            preview = ", ".join((extent_validation.get("mismatches") or [])[:10])
            raise RuntimeError(f"MVT tile extent mismatch (expected {extent}): {preview}")

        mvt_timings_payload = {
            **{k: round(v, 3) for k, v in stage_timings.items()},
        }
        gdal_result["timings"] = mvt_timings_payload
        conversions[mvt_key] = _conversion_entry(
            key=mvt_key, path=mvt_path, run_result=gdal_result, summary=mvt_summary,
            log_file=gdal_log, extent=extent, detail_offset=detail_offset,
            validation={
                "mode": validation_mode,
                "extent_validation": extent_validation,
            },
        )
        _emit(progress_callback, "convert", f"{mvt_key} completed: {mvt_summary.get('tile_count', 0)} tiles")

        _check_cancel(cancel_event)
        _emit(progress_callback, "mvt_to_mlt", f"Transcoding {variant_key} MVT to MLT")
        started = datetime.now(timezone.utc).isoformat()
        transcode_start = time.perf_counter()
        try:
            transcode_summary = transcode_mvt_pmtiles_to_mlt(
                mvt_path,
                mlt_path,
                validation_mode=validation_mode,
            )
            transcode_elapsed = time.perf_counter() - transcode_start
            stage_timings["mvt_to_mlt"] += transcode_elapsed
            stage_timings["mlt_validation"] += float((transcode_summary.get("validation") or {}).get("validation_seconds") or 0.0)

            if validation_mode == "full":
                validation = dict((transcode_summary.get("validation") or {}).get("full") or {})
                validation["mode"] = "full"
                exit_code = 0 if validation.get("passed") else 1
            elif validation_mode == "fast":
                lightweight = dict((transcode_summary.get("validation") or {}).get("lightweight") or {})
                source_tile_count = int(mvt_summary.get("tile_count") or 0)
                output_tile_count = int(transcode_summary.get("tile_count") or 0)
                validation = {
                    "mode": "fast",
                    "passed": source_tile_count == output_tile_count,
                    "source_tile_count": source_tile_count,
                    "output_tile_count": output_tile_count,
                    "lightweight": lightweight,
                    "mismatch_count": 0 if source_tile_count == output_tile_count else 1,
                    "mismatches": [] if source_tile_count == output_tile_count else ["tile_count differs"],
                }
                exit_code = 0 if validation["passed"] else 1
            else:
                validation = {
                    "mode": "none",
                    "passed": True,
                    "mismatch_count": 0,
                    "mismatches": [],
                }
                exit_code = 0

            stage_timings["total_postprocessing"] = round(
                stage_timings["mvt_scan"] + stage_timings["mvt_to_mlt"] + stage_timings["mlt_validation"],
                3,
            )
            combined_output = json.dumps({"transcoded": transcode_summary, "validation": validation}, indent=2)
        except Exception as exc:
            validation = {"passed": False, "error": str(exc)}
            exit_code = 1
            combined_output = str(exc)
            transcode_elapsed = time.perf_counter() - transcode_start
            stage_timings["mvt_to_mlt"] += transcode_elapsed
        elapsed = time.perf_counter() - transcode_start
        mlt_log = f"{name}_{mlt_key}.log"
        (logs_dir / mlt_log).write_text(combined_output, encoding="utf-8")
        mlt_summary = dict(mvt_summary)
        timings_payload = {
            **{k: round(v, 3) for k, v in stage_timings.items()},
        }
        conversions[mlt_key] = _conversion_entry(
            key=mlt_key,
            path=mlt_path,
            run_result={
                "exit_code": exit_code,
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "time_seconds": round(elapsed, 2),
                "time_ms": round(elapsed * 1000),
                "peak_memory_mb": None,
                "combined_output": combined_output,
                "timings": timings_payload,
            },
            summary=mlt_summary,
            log_file=mlt_log,
            extent=extent,
            detail_offset=detail_offset,
            validation={
                **validation,
                "mvt_extent_validation": extent_validation,
            },
        )
        _emit(progress_callback, "validation", f"{mlt_key} validation {'passed' if validation.get('passed') else 'failed'}")

    return conversions
