"""Source normalization stage: raw vector source -> canonical GeoPackage."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from . import normalization as _legacy


def detect_source(source_path: str | Path) -> dict[str, Any]:
    """Cheap source inspection: driver + layers without heavy feature scans."""
    source = Path(source_path)
    result = {
        "path": str(source),
        "driver": "unknown",
        "layers": [],
    }
    if not source.exists():
        return result

    try:
        completed = _legacy.subprocess.run(
            ["ogrinfo", "-ro", "-json", str(source)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception:
        return result

    if completed.returncode != 0:
        return result

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return result

    result["driver"] = str(payload.get("driverShortName") or payload.get("driver") or "unknown")
    for layer in payload.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        name = str(layer.get("name") or "").strip()
        if not name:
            continue
        result["layers"].append(name)
    return result


def apply_bounds(command: list[str], bounds: str | list[float] | tuple[float, ...] | None) -> list[str]:
    """Apply EPSG:4326 selection plus physical clipping to an ogr2ogr command."""
    parsed = _legacy._parse_bounds(bounds)
    if not parsed:
        return list(command)
    out = list(command)
    out.extend(["-spat_srs", "EPSG:4326", "-spat", *parsed])
    out.extend(["-clipsrc", "spat_extent"])
    return out


def get_layers_fast(source_path: str | Path) -> dict[str, Any]:
    """Get layer names and cheap/available feature counts in one pass."""
    source = Path(source_path)
    completed = _legacy.subprocess.run(
        ["ogrinfo", "-ro", "-json", str(source)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "")[-2000:]
        raise RuntimeError(f"ogrinfo failed for {source}: {tail}")

    payload = json.loads(completed.stdout or "{}")
    layers: list[dict[str, Any]] = []
    for item in payload.get("layers") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        raw_count = item.get("featureCount")
        count = None
        try:
            if raw_count is not None:
                parsed_count = int(raw_count)
                if parsed_count >= 0:
                    count = parsed_count
        except (TypeError, ValueError):
            count = None
        layers.append({"name": name, "feature_count": count})

    return {
        "driver": str(payload.get("driverShortName") or payload.get("driver") or "unknown"),
        "layers": layers,
        "raw": payload,
    }


def normalize_to_gpkg(
    *,
    dataset_name: str,
    source_path: str | Path,
    normalized_dir: str | Path,
    source_format: str,
    profile_plan: Mapping[str, Any],
    bounds: str | list[float] | tuple[float, ...] | None,
    normalized_crs: str = _legacy.DEFAULT_NORMALIZED_CRS,
    progress_callback=None,
    run_command=None,
) -> dict[str, Any]:
    """Normalize a source into one cacheable GPKG and record stage timing metadata."""
    started = time.perf_counter()
    result = _legacy.normalize_source_to_gpkg(
        dataset_name=dataset_name,
        source_path=source_path,
        normalized_dir=normalized_dir,
        source_format=source_format,
        profile_plan=profile_plan,
        bounds=bounds,
        normalized_crs=normalized_crs,
        progress_callback=progress_callback,
        run_command=run_command,
    )
    elapsed = time.perf_counter() - started
    manifest = dict(result.get("manifest") or {})
    manifest.setdefault("stage_timings", {})
    manifest["stage_timings"]["source_normalization"] = round(elapsed, 3)
    if result.get("manifest_path"):
        _legacy._write_json_atomic(Path(result["manifest_path"]), manifest)
    result["manifest"] = manifest
    return result


# Legacy-compatible exports
normalization_fingerprint = _legacy.normalization_fingerprint
sha256_file = _legacy.sha256_file
normalize_source_to_gpkg = _legacy.normalize_source_to_gpkg
build_normalization_command = _legacy.build_normalization_command
validate_normalized_gpkg = _legacy.validate_normalized_gpkg
available_disk_bytes = _legacy.available_disk_bytes
DEFAULT_NORMALIZED_CRS = _legacy.DEFAULT_NORMALIZED_CRS
