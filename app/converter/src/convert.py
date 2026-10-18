"""GEOMAPS Converter — download, analyze, convert, and record protocol."""

import argparse
import json
import re
import shutil
import time
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse, unquote

from .config import load_config
from .downloader import download_file
from .groundswell_handler import groundswell_to_gpkg, is_groundswell_url
from .analyzer import analyze_source, confirm_layers, get_source_format
from .process_metrics import get_output_size
from .gdal_tiles import run_gdal_dense_pipeline
from .normalize_source import available_disk_bytes, normalize_to_gpkg
from .protocol import (
    aggregate_conversion_runs,
    capture_environment,
    generate_protocol,
    load_protocol,
)
from .profile_rules import derive_profile_plan

KNOWN_SUFFIXES = (
    ".osm.pbf",
    ".geoparquet",
    ".geojson",
    ".mbtiles",
    ".pmtiles",
    ".parquet",
    ".gpkg",
    ".json",
    ".shp",
    ".gdb",
    ".zip",
    ".csv",
    ".tsv",
)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class ConversionCancelledError(RuntimeError):
    """Raised when a conversion job is cancelled by the user."""


def _tail_text(text, line_count=80, char_limit=8000):
    lines = text.splitlines()
    tailed = "\n".join(lines[-line_count:])
    if len(tailed) > char_limit:
        tailed = tailed[-char_limit:]
    return tailed


def _emit_progress(progress_callback, stage, message):
    if progress_callback is not None:
        progress_callback(stage, message)


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise ConversionCancelledError("Conversion cancelled by user")


def _parse_bounds(bounds_value):
    if bounds_value is None:
        return None
    if isinstance(bounds_value, str):
        token = bounds_value.strip()
        if not token:
            return None
        parts = [part.strip() for part in token.split(",")]
    elif isinstance(bounds_value, (list, tuple)):
        parts = [str(part).strip() for part in bounds_value]
    else:
        return None

    if len(parts) != 4:
        return None
    try:
        coords = [float(part) for part in parts]
    except ValueError:
        return None
    return ",".join(str(coord) for coord in coords)


def _summarize_log_line(line):
    line = ANSI_ESCAPE_RE.sub("", line).strip()
    if not line:
        return None
    if "argument:" in line:
        return None
    if line.endswith(" -"):
        return None
    if len(line) > 220:
        return f"...{line[-220:]}"
    return line


def _forward_log_progress(progress_callback, label, line):
    summary = _summarize_log_line(line)
    if summary is not None:
        _emit_progress(progress_callback, "convert", f"{label}: {summary}")


def _write_profile_plan_debug(debug_path, *, name, source_path, source_fmt, analysis, profile_plan):
    lines = [
        "=== PROFILE PLAN DEBUG ===",
        f"dataset: {name}",
        f"source_path: {source_path}",
        f"source_format: {source_fmt}",
        f"rule_name: {profile_plan.get('rule_name')}",
    ]

    available_layers = sorted(
        str((layer or {}).get("name") or "").strip()
        for layer in (analysis or {}).get("layers", [])
        if isinstance(layer, dict)
    )
    available_layers = [item for item in available_layers if item]
    lines.append(f"analysis_layer_count: {len(available_layers)}")
    if available_layers:
        lines.append("analysis_layers:")
        lines.extend(f"  - {item}" for item in available_layers)

    lines.append("planned_tile_layers:")
    known_layers = set(available_layers)
    for tile_layer in profile_plan.get("tile_layers") or []:
        layer_id = str(tile_layer.get("id") or "layer")
        source_layers = [str(item) for item in (tile_layer.get("source_layers") or []) if item]
        prefixes = [str(item) for item in (tile_layer.get("source_layer_prefixes") or []) if item]
        matched = [item for item in source_layers if item in known_layers]
        unmatched = [item for item in source_layers if item not in known_layers]
        zoom = tile_layer.get("zoom") or {}
        lines.append(f"- id: {layer_id}")
        lines.append(f"  source_layers: {', '.join(source_layers) if source_layers else '-'}")
        lines.append(f"  matched_source_layers: {', '.join(matched) if matched else '-'}")
        lines.append(f"  unmatched_source_layers: {', '.join(unmatched) if unmatched else '-'}")
        lines.append(f"  source_layer_prefixes: {', '.join(prefixes) if prefixes else '-'}")
        lines.append(f"  geometry_types: {', '.join(tile_layer.get('geometry_types') or []) or '-'}")
        lines.append(f"  class_field: {str(tile_layer.get('class_field') or '-')}")
        lines.append(f"  zoom: {zoom.get('min')}..{zoom.get('max')}")

    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_citygml_srs_debug(logs_dir, name, srs_diagnostics):
    if not srs_diagnostics:
        return None
    citygml_srs_log = Path(logs_dir) / f"{name}_citygml_srs_debug.log"
    lines = [
        "=== CITYGML SRS DIAGNOSTICS ===",
        f"dataset: {name}",
        f"layers: {len(srs_diagnostics)}",
    ]
    for item in srs_diagnostics:
        lines.append(f"layer: {item.get('layer', '-')}")
        lines.append(f"  member: {item.get('member', '-')}")
        lines.append(f"  detected_source_srs: {item.get('detected_source_srs') or '-'}")
        lines.append(f"  fallback_source_srs: {item.get('fallback_source_srs') or '-'}")
        lines.append(f"  effective_source_srs: {item.get('effective_source_srs') or '-'}")
        lines.append(f"  force_srs_detection: {item.get('force_srs_detection', False)}")
        lines.append(f"  last_attempt: {item.get('last_attempt', '-')}")
        lines.append(f"  last_exit_code: {item.get('last_exit_code', '-')}")
        lines.append(f"  status: {item.get('status', '-')}")
    citygml_srs_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return citygml_srs_log


def _write_citygml_skip_debug(logs_dir, name, tolerated_details):
    if not tolerated_details:
        return None
    citygml_skip_log = Path(logs_dir) / f"{name}_citygml_skip_debug.log"
    lines = [
        "=== CITYGML SKIP DETAILS ===",
        f"dataset: {name}",
        f"layers_with_skipfailures: {len(tolerated_details)}",
    ]
    for layer_name in sorted(tolerated_details.keys()):
        detail = tolerated_details[layer_name] or {}
        strict = detail.get("strict_pass") or {}
        retry = detail.get("retry_pass") or {}
        strict_reasons = strict.get("top_reasons") or []
        retry_reasons = retry.get("top_reasons") or []
        lines.append(f"layer: {layer_name}")
        lines.append(f"  strict_issue_count: {strict.get('issue_count', 0)}")
        lines.append(
            "  strict_top_reasons: "
            + (", ".join(f"{k}:{v}" for k, v in strict_reasons[:5]) or "-")
        )
        lines.append(f"  retry_issue_count: {retry.get('issue_count', 0)}")
        lines.append(
            "  retry_top_reasons: "
            + (", ".join(f"{k}:{v}" for k, v in retry_reasons[:5]) or "-")
        )
        strict_samples = strict.get("samples") or []
        if strict_samples:
            lines.append("  strict_samples:")
            for sample in strict_samples[:8]:
                lines.append(f"    - {sample}")
        retry_samples = retry.get("samples") or []
        if retry_samples:
            lines.append("  retry_samples:")
            for sample in retry_samples[:8]:
                lines.append(f"    - {sample}")
    citygml_skip_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return citygml_skip_log


def parse_args():
    parser = argparse.ArgumentParser(description="GEOMAPS Converter")
    parser.add_argument("--name", default=None, help="Dataset name (defaults to URL filename)")
    parser.add_argument("--url", required=True, help="Source URL or local path")
    parser.add_argument("--format", default="auto", help="Source format (osm.pbf, gpkg, geojson, shp, parquet, auto)")
    parser.add_argument("--heap", default=None, help="Java heap size (overrides config)")
    parser.add_argument("--profile", default=None, help="Dataset profile path")
    parser.add_argument("--area", default=None, help="Geofabrik area shortcut (e.g., monaco)")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--keep-intermediates", action="store_true", help="Keep all output files (don't clean up)")
    parser.add_argument("--debug-filtering", action="store_true", help="Write detailed layer/filter debug diagnostics into logs")
    parser.add_argument("--no-debug-filtering", action="store_true", help="Disable debug filtering diagnostics in logs")
    return parser.parse_args()


def _is_zip(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"PK\x03\x04"
    except Exception:
        return False


def _find_gdb_folder(names):
    """
    Return the normalized Path of the first .gdb directory in a zip's entry list.

    Handles Windows-style backslash separators in zip entries created on Windows.
    """
    for n in names:
        norm = n.replace("\\", "/")
        for parent in Path(norm).parents:
            if parent.suffix.lower() == ".gdb" and str(parent) != ".":
                return parent
    return None


# Priority order for the single-file formats. .gdb is handled separately: it is
# a directory, not a member.
ZIP_MEMBER_PRIORITY = [".gpkg", ".geojson", ".json", ".shp", ".parquet", ".geoparquet"]


def choose_zip_member(names):
    """The geospatial member to convert, and the same-priority ones rejected.

    Selection used to take the first match in ``zipfile.namelist()`` order,
    which makes the study's result a property of how the archive was packed.
    The Saentis download holds ``GPKG/de/078_Saentis.gpkg`` and
    ``GPKG/fr/078_Saentis.gpkg`` -- the German and French editions of one sheet,
    28 layers each with identical structure -- and German won because it happens
    to come first. Repacked the other way the pipeline would convert French
    attribute values with the same layer count and the same feature count, so no
    figure anywhere would change and nothing could detect that it had happened.

    Sorting makes the choice a property of the archive's contents instead. The
    rejected same-priority candidates are returned so a two-edition archive is
    visible in the protocol rather than only by opening the ZIP.

    Multiple candidates are deliberately not an error: ordinary UI imports of
    ordinary archives must keep working. The goal is determinism and a record.
    """
    for ext in ZIP_MEMBER_PRIORITY:
        matches = sorted(n for n in names if Path(n).suffix.lower() == ext)
        if matches:
            return matches[0], matches[1:]
    return None, []


def _extract_zip_source(zip_path, dest_dir):
    """
    Extract a zip archive and return the primary geospatial file inside it.

    Returns ``(path, member, alternatives)``: the extracted path, the archive
    member it came from, and the same-priority members that were not chosen.
    ``member`` is None for a .gdb directory, which is selected as a whole.

    Priority order: .gdb (dir) > .gpkg > .geojson > .json > .shp > .parquet / .geoparquet
    Returns ``(None, None, [])`` if no recognised geospatial file is found.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            # GDB: find the first .gdb directory, normalizing Windows backslashes.
            # Extract files manually so backslash-paths don't become literal filenames on Linux.
            gdb_folder = _find_gdb_folder(names)
            if gdb_folder is not None:
                gdb_prefix = str(gdb_folder) + "/"
                out_gdb = Path(dest_dir) / gdb_folder.name
                out_gdb.mkdir(parents=True, exist_ok=True)
                for n in names:
                    norm = n.replace("\\", "/")
                    if norm.startswith(gdb_prefix):
                        rel = norm[len(gdb_prefix):]
                        if rel:  # skip bare directory entries
                            out_file = out_gdb / rel
                            out_file.parent.mkdir(parents=True, exist_ok=True)
                            out_file.write_bytes(zf.read(n))
                return out_gdb, None, []

            # All other single-file formats
            candidate, alternatives = choose_zip_member(names)
            if candidate is None:
                return None, None, []

            # Some archives contain many shapefiles where lexicographic order
            # picks a tiny boundary layer first. Prefer the largest .shp member
            # so conversion starts from the most informative geometry payload.
            if Path(candidate).suffix.lower() == ".shp":
                shp_members = [n for n in names if Path(n).suffix.lower() == ".shp"]
                if len(shp_members) > 1:
                    ranked = sorted(
                        shp_members,
                        key=lambda member: zf.getinfo(member).file_size,
                        reverse=True,
                    )
                    candidate = ranked[0]
                    alternatives = [item for item in ranked[1:]]

            candidate_path = Path(candidate)
            candidate_dir = str(candidate_path.parent)
            candidate_stem = candidate_path.stem
            candidate_suffix = candidate_path.suffix.lower()

            # Shapefiles need sidecars with the same stem.
            for name in names:
                member_path = Path(name)
                if str(member_path.parent) != candidate_dir:
                    continue

                if member_path.name == candidate_path.name:
                    zf.extract(name, dest_dir)
                    continue

                if member_path.stem != candidate_stem:
                    continue

                if candidate_suffix == ".shp":
                    zf.extract(name, dest_dir)
                    continue

            return Path(dest_dir) / candidate, candidate, alternatives
    except zipfile.BadZipFile as exc:
        print(f"  Warning: could not unzip {zip_path}: {exc}")
        return None, None, []


def dataset_name_from_url(url):
    """Derive a filesystem-safe dataset name from a source URL or path."""
    parsed = urlparse(url)
    candidate = unquote(Path(parsed.path if parsed.scheme else url).name)
    if not candidate:
        candidate = "dataset"

    lowered = candidate.lower()
    changed = True
    while changed:
        changed = False
        for suffix in KNOWN_SUFFIXES:
            if lowered.endswith(suffix):
                candidate = candidate[:-len(suffix)]
                lowered = candidate.lower()
                changed = True
                break

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-._").lower()
    return slug or "dataset"


def _slugify(candidate):
    """Filesystem- and URL-safe form of a name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-._").lower()


def resolve_dataset_name(url, requested=None):
    """The name to file this dataset under: the caller's, or derived from the URL.

    The derived name is the protocol filename, every archive's prefix, every
    log name and the row label in results.md, and for two of the four study
    datasets it derives something the paper never says: the canonical Saentis
    URL gives "geologie-geocover_1115_2056" against the "geocover_1115_saentis"
    the documentation uses in 22 places, and the Groundswell collection URL
    gives "granules". A study import therefore states its name.

    A supplied name is still slugified -- it becomes a path segment, so being
    caller-supplied is not a reason to trust it -- but its suffixes are left
    alone, because it is a name rather than a filename.
    """
    if requested:
        slug = _slugify(requested)
        if slug:
            return slug
    return dataset_name_from_url(url)


def cleanup_targets(sources_dir, sidecars, *, keep_sources, keep_layerstats):
    """Return the paths post-conversion cleanup should delete.

    Sources are worth keeping so a dataset can be re-converted without
    re-downloading it (630 MB for the Louisiana wetlands). Layer stats sidecars
    are the raw evidence behind the per-layer metrics, so they are kept too.
    """
    targets = []
    if not keep_sources and sources_dir is not None:
        targets.append(sources_dir)
    if not keep_layerstats:
        targets.extend(sidecars)
    return targets


def cleanup_temp_dir(tmp_dir):
    """Delete files inside configured scratch, but keep final outputs intact."""
    if not tmp_dir:
        return
    temp_path = Path(tmp_dir)
    if not temp_path.exists():
        return
    for child in temp_path.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            pass


def _status_from_conversions(conversions):
    if not conversions:
        return "failed"
    if all((entry.get("exit_code") or 0) == 0 for entry in conversions.values()):
        return "completed"
    if any((entry.get("exit_code") or 0) == 0 for entry in conversions.values()):
        return "partial"
    return "failed"


def _unique_path(directory, filename):
    """Return a unique path, appending _1/_2/... if the file already exists."""
    directory = Path(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    idx = 1
    while True:
        alt = directory / f"{stem}_{idx}{suffix}"
        if not alt.exists():
            return alt
        idx += 1


def run_conversion_pipeline(
    *,
    name,
    url,
    source_format="auto",
    heap=None,
    profile=None,
    area=None,
    config_path=None,
    keep_intermediates=False,
    progress_callback=None,
    cancel_event=None,
    debug_filtering=None,
    pipeline_mode="full",
):
    _check_cancel(cancel_event)
    cfg = load_config(config_path)

    if heap:
        cfg["java_heap"] = heap
    if debug_filtering is not None:
        cfg["debug_filtering"] = bool(debug_filtering)
    else:
        cfg["debug_filtering"] = bool(cfg.get("debug_filtering", True))

    data_dir = Path(cfg["data_dir"])
    sources_dir = data_dir / "sources" / name
    output_dir = data_dir / "output"
    protocols_dir = data_dir / "protocols"
    logs_dir = data_dir / "logs"

    output_dir.mkdir(parents=True, exist_ok=True)
    protocols_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"GEOMAPS Converter: {name}")
    print(f"{'='*60}")
    _emit_progress(progress_callback, "start", f"Starting conversion for {name}")
    _check_cancel(cancel_event)

    # conversion_time_ms times Stage B alone: all variants start from the same
    # normalized GeoPackage, so folding Stage A preparation in would add an
    # identical constant to the four figures the study actually compares.
    # Preparation is therefore timed separately, once, as a dataset-level
    # figure. Stage A is timed separately and written to the normalization
    # manifest/protocol because it is dataset preparation, not MVT-vs-MLT
    # encoding cost.
    preparation_started = time.perf_counter()
    prepared = False
    source_member = None
    member_alternatives = []
    members_without_features = []

    source_path = None
    source_fmt = source_format if source_format != "auto" else "unknown"
    analysis = {"layers": []}
    stage_b_manifest = {}

    if pipeline_mode == "stage_b":
        source_path = Path(url)
        if not source_path.exists():
            source_path = data_dir / "normalized" / name / f"{name}.gpkg"
        if not source_path.exists():
            raise FileNotFoundError(f"Normalized GPKG not found for Stage B: {url}")
        source_fmt = "gpkg"
        analysis = analyze_source(source_path)
        manifest_path = source_path.with_suffix(".normalization.json")
        if manifest_path.exists():
            try:
                stage_b_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(f"Failed to read normalization manifest {manifest_path}: {exc}") from exc
        else:
            _emit_progress(
                progress_callback,
                "gpkg_preflight",
                "Normalization manifest not found; profile matching will fall back to GPKG identity",
            )
        _emit_progress(progress_callback, "gpkg_preflight", f"Using normalized GPKG: {source_path.name}")
    else:
        # ── Step 1: Download ─────────────────────────────────────────────
        print("\n[1/5] Downloading source...")
        _emit_progress(progress_callback, "download", f"Downloading source from {url}")
        _check_cancel(cancel_event)
        if is_groundswell_url(url):
            # One collection URL stands for 112 country archives, so acquisition,
            # verification and merge belong to the handler; the pipeline resumes at
            # an ordinary GeoPackage, as it does for CityGML and CSV.
            sources_dir.mkdir(parents=True, exist_ok=True)
            source_path = groundswell_to_gpkg(url, sources_dir, progress_callback)
            prepared = True
        elif url.startswith("http://") or url.startswith("https://"):
            source_path = download_file(url, sources_dir)
            prepared = True
        else:
            source_path = Path(url)
            if not source_path.exists():
                # Try relative to /data/sources/
                source_path = data_dir / "sources" / url
            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {url}")
            print(f"  Using local file: {source_path}")
        _emit_progress(progress_callback, "download", f"Source ready: {source_path.name}")
        _check_cancel(cancel_event)

    # ── Step 1b: Unzip (if archive) ──────────────────────────────────
    if pipeline_mode != "stage_b" and (source_path.suffix.lower() == ".zip" or _is_zip(source_path)):
        sources_dir.mkdir(parents=True, exist_ok=True)
        print("\n[1b/5] Extracting ZIP archive...")
        _emit_progress(progress_callback, "download", "Extracting ZIP archive...")
        _check_cancel(cancel_event)
        prepared = True
        extracted, source_member, member_alternatives = _extract_zip_source(
            source_path, sources_dir)
        if extracted is not None:
            print(f"  Extracted: {extracted.name}")
            _emit_progress(progress_callback, "download", f"Extracted: {extracted.name}")
            if member_alternatives:
                # Two editions of one sheet convert to identical counts, so this
                # line is the only place the choice is visible at run time.
                print(f"  Chose member {source_member} over "
                      f"{len(member_alternatives)}: {', '.join(member_alternatives)}")
            source_path = extracted
        else:
            print("  Warning: no recognisable geospatial file found inside the ZIP — proceeding with the archive as-is")

    # ── Step 2: Analyze ──────────────────────────────────────────────
    if pipeline_mode != "stage_b":
        print("\n[2/5] Analyzing source...")
        _check_cancel(cancel_event)
        source_fmt = source_format if source_format != "auto" else get_source_format(source_path)
        print(f"  Detected format: {source_fmt}")
        _emit_progress(progress_callback, "analyze", f"Detected source format: {source_fmt}")

    if source_fmt in {"tif", "tiff", "raster"}:
        raise RuntimeError(
            "Raster sources are no longer part of the active GEOMAPS research pipeline. "
            "Use a vector source that can be normalized to the canonical GeoPackage."
        )

    # For OSM PBF, ogrinfo is expensive and often incomplete; Stage A records
    # unknown feature counts instead of turning them into zero.
    if pipeline_mode != "stage_b" and source_fmt == "osm.pbf":
        analysis = {
            "file": source_path.name,
            "size_bytes": source_path.stat().st_size,
            "driver": "OSM/PBF",
            "description": f"OpenStreetMap extract: {name}",
            "layers": [],
        }
        msg = "OSM PBF detected — feature counts remain unknown until normalization/tiling"
        print(f"  {msg}")
        _emit_progress(progress_callback, "analyze", msg)
    elif pipeline_mode != "stage_b":
        analysis = analyze_source(source_path)

    total_features = sum(int((layer or {}).get('feature_count', 0) or 0) for layer in analysis.get('layers', []))
    print(f"  Source size: {analysis['size_bytes'] / (1024*1024):.2f} MB")
    print(f"  Layers: {len(analysis.get('layers', []))}")
    print(f"  Total features in analysis: {total_features}")
    _emit_progress(progress_callback, "analyze", f"Found {len(analysis.get('layers', []))} layers")
    for layer in analysis.get("layers", []):
        print(f"    - {layer['name']} ({layer['geometry_type']}, {layer['feature_count']} features)")

    if not analysis.get('layers'):
        print("  [analyze] WARNING: this source is empty at GDAL/ogrinfo level; GDAL cannot create non-empty vector tiles from it.")

    # ── Step 2b: GDB → GPKG (Planetiler cannot read GDB natively) ───
    if pipeline_mode != "stage_b" and source_fmt == "gdb":
        _check_cancel(cancel_event)
        sources_dir.mkdir(parents=True, exist_ok=True)
        gpkg_path = sources_dir / f"{name}.gpkg"
        print(f"\n[2b/5] Converting GDB → GeoPackage via ogr2ogr...")
        prepared = True
        _emit_progress(progress_callback, "analyze", "Converting GDB to GeoPackage (ogr2ogr)...")
        try:
            import subprocess as _sp
            result_ogr = _sp.run(
                ["ogr2ogr", "-f", "GPKG", "-t_srs", "EPSG:4326", str(gpkg_path), str(source_path)],
                capture_output=True, text=True, timeout=600,
            )
            if result_ogr.returncode != 0:
                raise RuntimeError(result_ogr.stderr.strip() or "ogr2ogr failed")
            print(f"  Converted: {gpkg_path.name} ({gpkg_path.stat().st_size / (1024*1024):.1f} MB)")
            _emit_progress(progress_callback, "analyze", f"GDB converted to GeoPackage: {gpkg_path.name}")
            source_path = gpkg_path
            source_fmt = "gpkg"
            # Re-analyze the converted GPKG (WGS84) so the protocol has correct extent and layers
            analysis = analyze_source(source_path)
            print(f"  Re-analyzed GPKG: {len(analysis.get('layers', []))} layers, extent={analysis.get('dataset', {}).get('extent')}")
            _emit_progress(progress_callback, "analyze", f"Re-analyzed GPKG: {len(analysis.get('layers', []))} layers")
        except FileNotFoundError:
            raise RuntimeError("ogr2ogr not found — ensure GDAL is installed in the container")

    # ── Step 2c: CSV → GPKG (Convert country-level time series to spatial) ──
    if pipeline_mode != "stage_b" and source_fmt == "csv":
        _check_cancel(cancel_event)
        sources_dir.mkdir(parents=True, exist_ok=True)
        gpkg_path = sources_dir / f"{name}.gpkg"
        print(f"\n[2c/5] Converting CSV → GeoPackage...")
        prepared = True
        _emit_progress(progress_callback, "analyze", "Converting CSV to GeoPackage (country centroids + data)...")
        try:
            from .csv_handler import csv_to_gpkg
            csv_to_gpkg(source_path, gpkg_path, progress_callback=progress_callback)
            print(f"  Converted: {gpkg_path.name} ({gpkg_path.stat().st_size / (1024*1024):.1f} MB)")
            _emit_progress(progress_callback, "analyze", f"CSV converted to GeoPackage: {gpkg_path.name}")
            source_path = gpkg_path
            source_fmt = "gpkg"
            # Analyze the converted GPKG
            analysis = analyze_source(source_path)
            print(f"  Analyzed GPKG: {len(analysis.get('layers', []))} layers")
            _emit_progress(progress_callback, "analyze", f"Analyzed GPKG: {len(analysis.get('layers', []))} layers")
        except ImportError:
            raise RuntimeError("csv_handler module not found")
        except Exception as e:
            raise RuntimeError(f"CSV conversion failed: {e}")

    # ── Step 2d: CityGML → GPKG (Convert 3D city models to vector tiles) ──
    if pipeline_mode != "stage_b" and source_fmt == "citygml":
        _check_cancel(cancel_event)
        sources_dir.mkdir(parents=True, exist_ok=True)
        gpkg_path = sources_dir / f"{name}.gpkg"
        print(f"\n[2d/5] Converting CityGML → GeoPackage...")
        prepared = True
        _emit_progress(progress_callback, "analyze", "Converting CityGML to GeoPackage (building features)...")
        try:
            from .citygml_handler import CityGMLConversionError, citygml_to_gpkg
            # Assemble in scratch space, not sources_dir: that lives on the
            # bind-mounted /data volume, where SQLite's incremental writes fail
            # partway through with "disk I/O error".
            citygml_result = citygml_to_gpkg(
                source_path,
                gpkg_path,
                progress_callback=progress_callback,
                temp_dir_parent=cfg.get("tmp_dir") or None,
                layer_timeout_seconds=cfg.get("citygml_layer_timeout_seconds", 3600),
                skip_timeout_layers=bool(cfg.get("citygml_skip_timeout_layers", False)),
                fallback_source_srs=str(cfg.get("citygml_fallback_source_srs") or "").strip() or None,
            )
            members_without_features = citygml_result.get("empty", [])
            tolerated_details = citygml_result.get("tolerated_details") or {}
            srs_diagnostics = citygml_result.get("srs_diagnostics") or []
            citygml_srs_log = _write_citygml_srs_debug(logs_dir, name, srs_diagnostics)
            if citygml_srs_log:
                print(f"  CityGML SRS debug log: {citygml_srs_log}")
                _emit_progress(progress_callback, "analyze", f"CityGML SRS diagnostics written: {citygml_srs_log.name}")
            citygml_skip_log = _write_citygml_skip_debug(logs_dir, name, tolerated_details)
            if citygml_skip_log:
                print(f"  CityGML skip debug log: {citygml_skip_log}")
                _emit_progress(progress_callback, "analyze", f"CityGML skip diagnostics written: {citygml_skip_log.name}")
            print(f"  Converted: {gpkg_path.name} ({gpkg_path.stat().st_size / (1024*1024):.1f} MB)")
            _emit_progress(progress_callback, "analyze", f"CityGML converted to GeoPackage: {gpkg_path.name}")
            source_path = gpkg_path
            source_fmt = "gpkg"
            # Analyze the converted GPKG
            analysis = analyze_source(source_path)
            print(f"  Analyzed GPKG: {len(analysis.get('layers', []))} layers")
            _emit_progress(progress_callback, "analyze", f"Analyzed GPKG: {len(analysis.get('layers', []))} layers")
        except ImportError:
            raise RuntimeError("citygml_handler module not found")
        except CityGMLConversionError as e:
            citygml_srs_log = _write_citygml_srs_debug(logs_dir, name, e.srs_diagnostics)
            if citygml_srs_log:
                print(f"  CityGML SRS debug log: {citygml_srs_log}")
                _emit_progress(progress_callback, "analyze", f"CityGML SRS diagnostics written: {citygml_srs_log.name}")
            citygml_skip_log = _write_citygml_skip_debug(logs_dir, name, e.tolerated_details)
            if citygml_skip_log:
                print(f"  CityGML skip debug log: {citygml_skip_log}")
                _emit_progress(progress_callback, "analyze", f"CityGML skip diagnostics written: {citygml_skip_log.name}")
            raise RuntimeError(f"CityGML conversion failed: {e}")
        except Exception as e:
            raise RuntimeError(f"CityGML conversion failed: {e}")

    # Everything above is preparation: acquiring the source and normalising it
    # into the one GeoPackage all four conversions start from. A dataset that
    # needed neither -- a local file already in its final form, as Amsterdam now
    # is because the PDOK extract URL expired -- records no figure at all rather
    # than a misleading small one.
    preparation_time_ms = (
        round((time.perf_counter() - preparation_started) * 1000) if prepared else None
    )

    # Profile selection must use the original dataset identity, not the fact that
    # Stage A happens to store it as GPKG. This keeps OSM/GML/etc. profile rules
    # stable across the Stage-A/Stage-B boundary.
    profile_source_path = str(source_path)
    profile_source_fmt = source_fmt
    if pipeline_mode == "stage_b" and stage_b_manifest:
        profile_source_path = str(stage_b_manifest.get("source_filename") or source_path)
        profile_source_fmt = str(stage_b_manifest.get("source_type") or source_fmt)

    profile_plan = derive_profile_plan(
        dataset_name=name,
        source_path=profile_source_path,
        source_format=profile_source_fmt,
        analysis=analysis,
        rules_path=cfg.get("profile_rules_path"),
    )
    plan_output = profile_plan.get("output") or {}
    plan_min_zoom = int(plan_output.get("min_zoom", cfg.get("min_zoom", 0)))
    plan_max_zoom = int(plan_output.get("max_zoom", cfg.get("max_zoom", 14)))
    plan_bounds = _parse_bounds(plan_output.get("bounds"))

    if str(profile_plan.get("source_kind") or "").lower() == "raster":
        raise RuntimeError(
            "The selected dataset profile is raster, but the active GEOMAPS pipeline is vector-only."
        )

    normalized_manifest = {}
    if pipeline_mode != "stage_b":
        # ── Stage A: Normalize ───────────────────────────────────────────
        normalized_root = Path(cfg.get("normalized_dir") or (data_dir / "normalized"))
        normalized_dir = normalized_root / name
        free_bytes = available_disk_bytes(normalized_root if normalized_root.exists() else data_dir)
        _emit_progress(
            progress_callback,
            "normalize",
            f"Free space before normalization: {free_bytes / (1024 * 1024 * 1024):.1f} GB",
        )
        normalization_result = normalize_to_gpkg(
            dataset_name=name,
            source_path=source_path,
            normalized_dir=normalized_dir,
            source_format=source_fmt,
            profile_plan=profile_plan,
            bounds=plan_bounds,
            normalized_crs=str(cfg.get("normalization_crs") or "EPSG:3857"),
            progress_callback=progress_callback,
        )
        normalized_manifest = normalization_result.get("manifest") or {}
        source_path = Path(normalization_result["path"])
        source_fmt = "gpkg"
        analysis = analyze_source(source_path)
    else:
        normalized_manifest = stage_b_manifest
        normalization_result = {
            "path": source_path,
            "manifest_path": source_path.with_suffix(".normalization.json"),
            "artifact_status": "reused_from_cache",
            "manifest": normalized_manifest,
        }

    # Keep the original profile plan. Only the analysis is refreshed from the
    # normalized GPKG; re-deriving the profile as source_format=gpkg can select a
    # different rule and radically change the amount of work in Stage B.
    plan_output = profile_plan.get("output") or {}
    plan_min_zoom = int(plan_output.get("min_zoom", cfg.get("min_zoom", 0)))
    plan_max_zoom = int(plan_output.get("max_zoom", cfg.get("max_zoom", 14)))
    plan_bounds = _parse_bounds(plan_output.get("bounds") or normalized_manifest.get("bounds"))

    if pipeline_mode == "stage_a":
        _emit_progress(progress_callback, "done", "Stage A normalization completed")
        return {
            "status": "completed",
            "stage": "stage_a",
            "normalized": {
                "gpkg": str(source_path),
                "manifest": str(normalization_result.get("manifest_path") or ""),
                "artifact_status": normalization_result.get("artifact_status"),
            },
        }

    debug_filtering_enabled = bool(cfg.get("debug_filtering", False))
    plan_debug_path = logs_dir / f"{name}_profile_plan_debug.log"
    profile_debug_path = logs_dir / f"{name}_profile_filter_debug.log"
    if debug_filtering_enabled:
        _write_profile_plan_debug(
            plan_debug_path,
            name=name,
            source_path=str(source_path),
            source_fmt=source_fmt,
            analysis=analysis,
            profile_plan=profile_plan,
        )
        print(f"  Profile plan debug log: {plan_debug_path}")
        _emit_progress(progress_callback, "convert", f"Profile plan debug written: {plan_debug_path.name}")

    # ── Step 3: Convert ──────────────────────────────────────────────
    print("\n[3/5] Converting outputs...")
    _emit_progress(progress_callback, "convert", "Running conversions")
    _check_cancel(cancel_event)
    conversions = {}

    # Stage B: tile the canonical GPKG into MVT/MBTiles, directly repack those
    # ready-made tiles into PMTiles, then transcode each MVT archive to MLT.
    analysis = confirm_layers(analysis, source_path)
    print(f"  GDAL tiling source layer count: {len(analysis.get('layers', []))}")
    conversions = run_gdal_dense_pipeline(
        name=name,
        source_path=source_path,
        output_dir=output_dir,
        logs_dir=logs_dir,
        profile_plan=profile_plan,
        analysis=analysis,
        min_zoom=plan_min_zoom,
        max_zoom=plan_max_zoom,
        bounds=plan_bounds,
        tmp_dir=cfg.get("tmp_dir") or None,
        variants=cfg.get("gdal_dense_variants"),
        progress_callback=progress_callback,
        cancel_event=cancel_event,
        log_progress=lambda label, line: _forward_log_progress(progress_callback, label, line),
        simplification=float(cfg.get("gdal_simplification", 1.6)),
        simplification_max_zoom=float(cfg.get("gdal_simplification_max_zoom", 1.0)),
        max_size=int(cfg.get("gdal_max_size", 2147483647)),
        max_features=int(cfg.get("gdal_max_features", 2147483647)),
        validation_mode=str(cfg.get("gdal_validation_mode", "fast")),
        tile_limits_mode=str(cfg.get("gdal_tile_limits_mode", "experimental_unlimited")),
    )

    # ── Step 3b: Backfill OSM layers from conversion stats ──────────
    # OSM PBF skips ogrinfo analysis; reconstruct layer list from the generated
    # standard MVT archive.
    if source_fmt == "osm.pbf" and not analysis.get("layers"):
        conv_layers = (
            conversions.get("standard_mvt", {}).get("layers")
            or conversions.get("standard_mlt", {}).get("layers")
            or {}
        )
        total_features = (
            conversions.get("standard_mvt", {}).get("feature_count")
            or conversions.get("standard_mlt", {}).get("feature_count")
            or 0
        )
        analysis["layers"] = [
            {
                "name": layer_name,
                "feature_count": stats.get("feature_count", 0),
                "geometry_type": "Mixed",
                "crs": "",
                "extent": [],
                "fields": [],
            }
            for layer_name, stats in conv_layers.items()
        ]
        # Store total at dataset level so the frontend can use it as a fallback
        analysis.setdefault("dataset", {})["feature_count"] = total_features
        print(f"  Backfilled {len(analysis['layers'])} OSM layers, total features: {total_features:,}")
        _emit_progress(progress_callback, "analyze", f"Backfilled {len(analysis['layers'])} OSM layers")

    # ── Step 4: Generate Protocol ────────────────────────────────────
    print("\n[4/5] Generating protocol...")
    _emit_progress(progress_callback, "protocol", "Generating protocol JSON")
    _check_cancel(cancel_event)
    dataset_info = {
        "name": name,
        "url": url,
        "format": source_fmt,
        # What was actually converted, and what was passed over getting there.
        # dataset.url names the archive, which for a multi-edition download is
        # not enough to say which map the figures describe.
        "source_member": source_member,
        "source_member_alternatives": member_alternatives,
        "source_members_without_features": members_without_features,
        "preparation_time_ms": preparation_time_ms,
        "normalization": {
            "gpkg": str(source_path),
            "manifest": str(normalization_result.get("manifest_path")),
            "artifact_status": normalization_result.get("artifact_status"),
            "normalization_time_ms": normalized_manifest.get("normalization_time_ms"),
            "gpkg_sha256": normalized_manifest.get("gpkg_sha256"),
            "fingerprint": normalized_manifest.get("fingerprint"),
        },
    }
    protocol_path = generate_protocol(
        dataset_info, analysis, conversions, protocols_dir,
        environment=capture_environment(cfg),
    )
    # generate_protocol already writes the compact v2 payload to disk.
    protocol = load_protocol(protocol_path)
    overall_status = _status_from_conversions(conversions)

    # ── Step 5: Cleanup ──────────────────────────────────────────────
    print("\n[5/5] Cleaning up...")
    _emit_progress(progress_callback, "cleanup", "Cleaning up intermediate files")
    _check_cancel(cancel_event)
    # Output archives are always kept — they are what the benchmark measures.
    keep_sources = keep_intermediates or bool(cfg.get("keep_sources", True))
    keep_layerstats = keep_intermediates or bool(cfg.get("keep_layerstats", True))

    sidecars = []

    temp_dir = cfg.get("tmp_dir") or "/planetiler-tmp"
    cleanup_temp_dir(temp_dir)

    removed = cleanup_targets(
        sources_dir if sources_dir.exists() else None,
        [s for s in sidecars if s.exists()],
        keep_sources=keep_sources,
        keep_layerstats=keep_layerstats,
    )
    for target in removed:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        print(f"  Removed: {target}")
    if not removed:
        print(f"  Kept sources ({keep_sources}) and layer stats ({keep_layerstats})")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Conversion complete!")
    print(f"{'='*60}")
    _emit_progress(progress_callback, "done", f"Finished with status {overall_status}")
    for key, data in sorted(conversions.items()):
        size_mb = data["size_bytes"] / (1024 * 1024) if data["size_bytes"] else 0
        mem_mb = data.get("peak_memory_mb", 0)
        mem_str = f"  {mem_mb:.0f} MB RAM" if mem_mb else ""
        failed_step = data.get("failed_step")
        if failed_step:
            status = f"FAILED at {failed_step}"
        elif data["exit_code"] == 0:
            status = "OK"
        else:
            status = f"FAILED (exit {data['exit_code']})"
        print(f"  {key:<20} {size_mb:>8.2f} MB  {data['tile_count']:>8} tiles  {data['time_seconds']:>6.1f}s{mem_str}  [{status}]")
    ratios = protocol.get("compression_ratios", {})
    if ratios:
        print(f"\nCompression ratios:")
        for label, value in ratios.items():
            if isinstance(value, (int, float)):
                print(f"  {label}: {value:.4f}")
            else:
                print(f"  {label}: {value}")

    return {
        "status": overall_status,
        "conversions": conversions,
        "protocol_path": str(protocol_path),
    }


def main():
    args = parse_args()
    name = args.name or dataset_name_from_url(args.url)
    debug_filtering = args.debug_filtering and not args.no_debug_filtering

    try:
        run_conversion_pipeline(
            name=name,
            url=args.url,
            source_format=args.format,
            heap=args.heap,
            profile=args.profile,
            area=args.area,
            config_path=args.config,
            keep_intermediates=args.keep_intermediates,
            debug_filtering=debug_filtering,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

