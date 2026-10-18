"""Analyze source geospatial files using GDAL/OGR."""

import json
import subprocess
import time
from pathlib import Path


def _transform_extent_to_wgs84(extent, crs):
    """Transform extent [minx, miny, maxx, maxy] to WGS84 (EPSG:4326) via gdaltransform."""
    if not extent or len(extent) != 4:
        return None
    if not crs or crs == "Unknown" or "4326" in crs:
        return extent

    minx, miny, maxx, maxy = extent
    # Feed all 4 corners so we handle rotated projections correctly
    stdin = f"{minx} {miny}\n{maxx} {miny}\n{minx} {maxy}\n{maxx} {maxy}\n"
    try:
        result = subprocess.run(
            ["gdaltransform", "-s_srs", crs, "-t_srs", "EPSG:4326"],
            input=stdin, capture_output=True, text=True, check=True, timeout=30,
        )
        lons, lats = [], []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                lons.append(float(parts[0]))
                lats.append(float(parts[1]))
        if lons and lats:
            return [min(lons), min(lats), max(lons), max(lats)]
    except Exception as e:
        print(f"  Warning: extent transformation failed ({e})")
    return None


def _log_analysis_summary(source_path, analysis, stage):
    layers = analysis.get("layers") or []
    total_features = sum(int((layer or {}).get("feature_count", 0) or 0) for layer in layers)
    names = [str((layer or {}).get("name") or "").strip() for layer in layers if isinstance(layer, dict)]
    names = [name for name in names if name][:12]
    print(
        f"  [analysis:{stage}] {Path(source_path).name}: "
        f"{len(layers)} layers, {total_features} features total; sample={', '.join(names) if names else 'none'}"
    )
    if not layers:
        print(f"  [analysis:{stage}] WARNING: source reported zero layers; check ogrinfo / GDAL read before conversion.")


def confirm_layers(analysis, source_path, analyse=None, attempts=3, delay=2.0, sleep=None):
    """Return an analysis that names at least one layer, re-reading if it does not.

    A GeoPackage written moments earlier can read back as empty. On 2026-08-29
    the Amsterdam archive was finalised at 18:07:28 and opened at 18:07:37; both
    `ogrinfo -json -so` here and `PRAGMA foreign_key_check` inside Planetiler
    failed on it, and both succeeded on the same bytes afterwards. So an empty
    first answer is re-read rather than believed.

    When it stays empty the caller must not continue. `generate_vector_profile`
    answers an empty layer list with one catch-all layer carrying no attributes,
    which is what the 18:07 run produced: 30 BGT featuretypes encoded as a single
    attribute-less layer. Sizes measured from that are not sizes of this dataset,
    and a study about attribute encoding cannot report them.
    """
    if analysis.get("layers"):
        _log_analysis_summary(source_path, analysis, "confirm_layers")
        return analysis

    analyse = analyse or analyze_source
    sleep = sleep or time.sleep

    for attempt in range(2, attempts + 1):
        sleep(delay)
        print(f"  Source reported no layers; re-reading ({attempt}/{attempts})...")
        analysis = analyse(source_path)
        if analysis.get("layers"):
            _log_analysis_summary(source_path, analysis, f"confirm_layers_retry_{attempt}")
            return analysis

    print(f"  [analysis:confirm_layers] ERROR: {Path(source_path).name} still reports zero layers after {attempts} reads.")
    raise RuntimeError(
        f"{Path(source_path).name} reports no layers after {attempts} reads. "
        "Refusing to convert: a source with no layers yields a single catch-all "
        "tile layer carrying no attributes, whose size is not a measurement of "
        "this dataset."
    )


def analyze_source(source_path):
    """
    Analyze a geospatial source file using ogrinfo.

    Returns a dict with dataset metadata and per-layer info.
    """
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    result = {
        "file": source_path.name,
        "size_bytes": source_path.stat().st_size,
        "layers": [],
    }

    # Get dataset info in JSON format
    try:
        ogrinfo_out = subprocess.run(
            ["ogrinfo", "-json", "-so", str(source_path)],
            capture_output=True, text=True, check=True, timeout=300,
        )
        info = json.loads(ogrinfo_out.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        print(f"  Warning: ogrinfo JSON failed ({e}), falling back to text mode")
        return _analyze_text_mode(source_path, result)

    # Parse dataset-level info
    ds_meta = info.get("metadata", {})
    result["description"] = info.get("description", "")
    result["driver"] = info.get("driverShortName", "")
    result["metadata"] = ds_meta

    # Parse layers and compute combined extent
    combined_extent = None
    combined_crs = None
    for layer in info.get("layers", []):
        layer_extent = (
            layer.get("geometryFields", [{}])[0].get("extent", [])
            if layer.get("geometryFields") else []
        )
        layer_crs = _extract_crs(layer)
        layer_info = {
            "name": layer.get("name", ""),
            "feature_count": layer.get("featureCount", 0),
            "geometry_type": layer.get("geometryFields", [{}])[0].get("type", "Unknown")
                if layer.get("geometryFields") else "Unknown",
            "crs": layer_crs,
            "extent": layer_extent,
            "fields": [
                {"name": f.get("name", ""), "type": f.get("type", "")}
                for f in layer.get("fields", [])
            ],
        }
        result["layers"].append(layer_info)
        
        # Merge layer extent into combined extent
        if layer_extent and len(layer_extent) == 4:
            if combined_extent is None:
                combined_extent = list(layer_extent)
                combined_crs = layer_crs
            else:
                combined_extent[0] = min(combined_extent[0], layer_extent[0])
                combined_extent[1] = min(combined_extent[1], layer_extent[1])
                combined_extent[2] = max(combined_extent[2], layer_extent[2])
                combined_extent[3] = max(combined_extent[3], layer_extent[3])

    # Store combined extent at dataset level, transformed to WGS84
    if combined_extent:
        wgs84_extent = _transform_extent_to_wgs84(combined_extent, combined_crs)
        result["dataset"] = {
            "extent": wgs84_extent if wgs84_extent else combined_extent,
            "crs": "EPSG:4326" if wgs84_extent else combined_crs,
        }

    _log_analysis_summary(source_path, result, "analyze_source")
    return result


def _extract_crs(layer):
    """Extract CRS string from ogrinfo layer data."""
    geom_fields = layer.get("geometryFields", [])
    if not geom_fields:
        return "Unknown"
    crs_info = geom_fields[0].get("coordinateSystem", {})
    authority = crs_info.get("projjson", {}).get("id", {})
    if authority:
        return f"{authority.get('authority', 'EPSG')}:{authority.get('code', '?')}"
    wkt = crs_info.get("wkt", "")
    if "EPSG" in wkt:
        # Try to extract EPSG from WKT
        parts = wkt.split('"EPSG"')
        if len(parts) > 1:
            code = parts[-1].strip().strip(",").strip("]").strip()
            return f"EPSG:{code}"
    return "Unknown"


def _analyze_text_mode(source_path, result):
    """Fallback: parse ogrinfo text output for basic layer info."""
    try:
        out = subprocess.run(
            ["ogrinfo", "-so", str(source_path)],
            capture_output=True, text=True, check=True, timeout=300,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return result

    for line in out.stdout.splitlines():
        line = line.strip()
        # Lines like: "1: layer_name (Polygon)"
        if line and line[0].isdigit() and ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                rest = parts[1].strip()
                geom_type = "Unknown"
                name = rest
                if "(" in rest and ")" in rest:
                    name = rest[:rest.rfind("(")].strip()
                    geom_type = rest[rest.rfind("(") + 1:rest.rfind(")")].strip()
                result["layers"].append({
                    "name": name,
                    "geometry_type": geom_type,
                    "feature_count": 0,
                    "fields": [],
                })

    return result


def get_source_format(source_path):
    """Detect the format of a source file by extension."""
    ext = Path(source_path).suffix.lower()
    format_map = {
        ".pbf": "osm.pbf",
        ".osm": "osm.pbf",
        ".gpkg": "gpkg",
        ".geojson": "geojson",
        ".json": "geojson",
        ".shp": "shp",
        ".parquet": "parquet",
        ".geoparquet": "parquet",
        ".tif": "tif",
        ".tiff": "tif",
        ".gdb": "gdb",
        ".csv": "csv",
        ".tsv": "csv",
        ".gml": "citygml",
    }
    if ext == ".zip":
        return _detect_zip_format(source_path)
    # .gdb is a directory — also match if the path itself is a directory ending in .gdb
    if source_path.is_dir() and ext == ".gdb":
        return "gdb"
    return format_map.get(ext, "unknown")


def _detect_zip_format(zip_path):
    """Detect the primary geospatial format inside a zip archive."""
    import zipfile as _zipfile

    priority = [".gpkg", ".geojson", ".json", ".shp", ".parquet", ".geoparquet", ".tif", ".tiff", ".csv", ".tsv", ".gml"]
    fmt_map = {
        ".gpkg": "gpkg",
        ".geojson": "geojson",
        ".json": "geojson",
        ".shp": "shp",
        ".parquet": "parquet",
        ".geoparquet": "parquet",
        ".tif": "tif",
        ".tiff": "tif",
        ".csv": "csv",
        ".tsv": "csv",
        ".gml": "citygml",
    }
    try:
        with _zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        # GDB: normalize Windows backslashes before checking path hierarchy
        if any(
            p.suffix.lower() == ".gdb" and str(p) != "."
            for n in names
            for p in Path(n.replace("\\", "/")).parents
        ):
            return "gdb"
        for ext in priority:
            if any(Path(n).suffix.lower() == ext for n in names):
                return fmt_map[ext]
    except Exception:
        pass
    # Fallback: infer from stem (e.g. "dataset_gpkg.zip" or "citygml_nl.zip")
    stem = Path(zip_path).stem.lower()
    for keyword, fmt in [("gpkg", "gpkg"), ("geojson", "geojson"), ("shp", "shp"), ("tif", "tif"), ("tiff", "tif"), ("csv", "csv"), ("citygml", "citygml"), ("gml", "citygml")]:
        if keyword in stem:
            return fmt
    return "unknown"
