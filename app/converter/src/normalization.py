"""Stage A normalization into a reusable canonical GeoPackage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


NORMALIZATION_SCHEMA_VERSION = 2
DEFAULT_NORMALIZED_CRS = "EPSG:3857"
ProgressCallback = Callable[[str, str], None]


def _emit(progress_callback: ProgressCallback | None, stage: str, message: str) -> None:
    if progress_callback is not None:
        progress_callback(stage, message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_bounds(bounds: str | list[float] | tuple[float, ...] | None) -> list[str] | None:
    if bounds is None:
        return None
    if isinstance(bounds, str):
        parts = [part.strip() for part in bounds.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in bounds]
    if len(parts) != 4:
        return None
    try:
        return [str(float(part)) for part in parts]
    except (TypeError, ValueError):
        return None


def normalization_fingerprint(
    *,
    source_sha256: str,
    profile_plan: Mapping[str, Any],
    bounds: str | list[float] | tuple[float, ...] | None,
    normalized_crs: str,
    gdal_version: str | None = None,
) -> dict[str, Any]:
    """Return the cache identity for a normalized GeoPackage."""
    normalization_rules = dict((profile_plan or {}).get("normalization") or {})
    return {
        "schema_version": NORMALIZATION_SCHEMA_VERSION,
        "source_sha256": source_sha256,
        # Only Stage-A settings belong in the normalization cache key. Tiling
        # zooms/layer mappings may change without requiring a new GeoPackage.
        "normalization_rules_hash": _stable_json_sha256(normalization_rules),
        "bounds": _parse_bounds(bounds),
        "clip_to_bounds": bool(_parse_bounds(bounds)),
        "normalized_crs": str(normalized_crs or DEFAULT_NORMALIZED_CRS),
        "make_valid": bool(normalization_rules.get("make_valid", False)),
        "gdal_version": gdal_version or "unknown",
    }


def build_normalization_command(
    *,
    source_path: Path,
    output_path: Path,
    bounds: str | list[float] | tuple[float, ...] | None,
    normalized_crs: str = DEFAULT_NORMALIZED_CRS,
    make_valid: bool = False,
) -> list[str]:
    """Build Stage A: crop once, flatten to XY, reproject once, write indexed GPKG.

    `-spat` avoids reading irrelevant features and `-clipsrc spat_extent`
    physically clips selected geometries before reprojection.
    """
    cmd = [
        "ogr2ogr",
        "-progress",
        "-f",
        "GPKG",
        str(output_path),
        str(source_path),
        "-t_srs",
        str(normalized_crs or DEFAULT_NORMALIZED_CRS),
        "-dim",
        "XY",
        "-gt",
        "65536",
        "-lco",
        "SPATIAL_INDEX=YES",
    ]
    if make_valid:
        cmd.append("-makevalid")
    parsed_bounds = _parse_bounds(bounds)
    if parsed_bounds:
        cmd.extend(["-spat_srs", "EPSG:4326", "-spat", *parsed_bounds])
        cmd.extend(["-clipsrc", "spat_extent"])
    return cmd


def _gdal_version() -> str:
    try:
        result = subprocess.run(["ogr2ogr", "--version"], capture_output=True, text=True, timeout=20)
    except Exception:
        return "unknown"
    return (result.stdout or result.stderr or "").strip() or "unknown"


def inspect_gpkg(path: Path) -> dict[str, Any]:
    result = subprocess.run(["ogrinfo", "-ro", "-json", str(path)], capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ogrinfo failed")
    try:
        meta = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ogrinfo returned non-JSON output: {exc}") from exc

    layers = []
    for layer in meta.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        feature_count = layer.get("featureCount")
        if feature_count is None or int(feature_count) < 0:
            count_value = None
        else:
            count_value = int(feature_count)
        layers.append(
            {
                "name": str(layer.get("name") or ""),
                "feature_count": count_value,
                "geometry_type": layer.get("geometryType") or layer.get("geometry_type") or "Unknown",
                "crs": (
                    ((layer.get("geometryFields") or [{}])[0].get("coordinateSystem") or {}).get("id")
                    if isinstance(layer.get("geometryFields"), list)
                    else None
                ),
            }
        )
    return {"layers": layers, "raw": meta}


def validate_normalized_gpkg(
    path: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    expected_crs: str = DEFAULT_NORMALIZED_CRS,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"Normalized GPKG is missing or empty: {path}")

    with closing(sqlite3.connect(path)) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise RuntimeError(f"SQLite integrity_check failed for {path}: {integrity}")
        gpkg_layers = conn.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type IN ('features', 'attributes')"
        ).fetchall()
        geometry_rows = conn.execute(
            "SELECT table_name, column_name, srs_id FROM gpkg_geometry_columns"
        ).fetchall()
        sqlite_objects = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()
        }

    expected_epsg = None
    token = str(expected_crs or "").strip().upper()
    if token.startswith("EPSG:"):
        try:
            expected_epsg = int(token.split(":", 1)[1])
        except ValueError:
            expected_epsg = None

    wrong_crs = [
        f"{table}:{srs_id}"
        for table, _column, srs_id in geometry_rows
        if expected_epsg is not None and int(srs_id) != expected_epsg
    ]
    if wrong_crs:
        raise RuntimeError(
            f"Normalized GPKG CRS mismatch; expected {expected_crs}, got {', '.join(wrong_crs[:20])}"
        )

    missing_spatial_indexes = [
        table
        for table, column, _srs_id in geometry_rows
        if f"rtree_{table}_{column}" not in sqlite_objects
    ]
    if missing_spatial_indexes:
        raise RuntimeError(
            "Normalized GPKG is missing spatial indexes for: "
            + ", ".join(missing_spatial_indexes[:20])
        )

    inspection = inspect_gpkg(path)
    layers = [layer for layer in inspection.get("layers") or [] if layer.get("name")]
    if not layers:
        raise RuntimeError(f"Normalized GPKG has no readable layers: {path}")

    if manifest:
        if "bounds" not in manifest:
            raise RuntimeError("Normalization manifest is missing bounds")
        if not manifest.get("normalized_crs"):
            raise RuntimeError("Normalization manifest is missing normalized_crs")
        if not manifest.get("stable_id_strategy"):
            raise RuntimeError("Normalization manifest is missing stable_id_strategy")

    return {
        "layer_count": len(layers),
        "layers": layers,
        "gpkg_content_layers": [row[0] for row in gpkg_layers],
        "spatial_index_count": len(geometry_rows),
        "missing_spatial_indexes": missing_spatial_indexes,
        "expected_crs": expected_crs,
    }


def _manifest_path_for(gpkg_path: Path) -> Path:
    return gpkg_path.with_suffix(".normalization.json")


def _load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    partial.replace(path)


def _directory_snapshot(path: Path) -> str:
    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name)
    except Exception as exc:
        return f"<failed to list {path}: {exc}>"

    rows = []
    for entry in entries[:30]:
        try:
            size = entry.stat().st_size if entry.is_file() else "<dir>"
        except Exception:
            size = "<unknown>"
        rows.append(f"{entry.name} ({size})")
    if len(entries) > 30:
        rows.append(f"... {len(entries) - 30} more")
    return ", ".join(rows) or "<empty>"


def _try_lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError(str(exc)) from exc
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _stage_a_dataset_lock(
    *,
    normalized_dir: Path,
    dataset_name: str,
    progress_callback: ProgressCallback | None,
    timeout_seconds: float = 900.0,
):
    """Serialize Stage A for one dataset across processes/containers."""
    locks_dir = normalized_dir / ".locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_path = locks_dir / f"{dataset_name}.stage_a.lock"
    lock_path.touch(exist_ok=True)

    handle = lock_path.open("a+b")
    start = time.monotonic()
    announced_wait = False
    try:
        while True:
            try:
                _try_lock_file(handle)
                break
            except BlockingIOError:
                if not announced_wait:
                    _emit(progress_callback, "normalize", f"Waiting for Stage A lock: {dataset_name}")
                    announced_wait = True
                if (time.monotonic() - start) >= timeout_seconds:
                    raise RuntimeError(
                        "Timed out waiting for Stage A dataset lock: "
                        f"{lock_path} (>{int(timeout_seconds)}s)."
                    )
                time.sleep(0.2)
        yield
    finally:
        try:
            _unlock_file(handle)
        finally:
            handle.close()


def _prepare_gpkg_target_slot(gpkg_path: Path) -> None:
    """Ensure the target path for a normalized GPKG is a writable file slot.

    Some interrupted/legacy runs can leave `<dataset>.gpkg` as a directory.
    Recover automatically when this directory is empty; otherwise fail with
    a clear diagnostic because automatic cleanup would risk data loss.
    """
    if not gpkg_path.exists():
        return
    if gpkg_path.is_file():
        return
    if not gpkg_path.is_dir():
        raise RuntimeError(f"Normalized GPKG target is neither file nor directory: {gpkg_path}")

    children = sorted(gpkg_path.iterdir(), key=lambda item: item.name)
    if children:
        preview = ", ".join(child.name for child in children[:20])
        if len(children) > 20:
            preview += f", ... {len(children) - 20} more"
        raise RuntimeError(
            "Normalized GPKG target path is a non-empty directory and cannot be replaced safely: "
            f"{gpkg_path} (children: {preview})"
        )

    gpkg_path.rmdir()


def _looks_like_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _ensure_normalized_dir(
    *,
    normalized_dir: Path,
    dataset_name: str,
    progress_callback: ProgressCallback | None,
) -> None:
    """Ensure normalized_dir is a directory, handling legacy file collisions."""
    if normalized_dir.exists() and normalized_dir.is_dir():
        return

    if normalized_dir.exists() and normalized_dir.is_file():
        if not _looks_like_sqlite(normalized_dir):
            raise RuntimeError(
                "Normalized output path is occupied by a file that is not a SQLite/GPKG artifact: "
                f"{normalized_dir}. Move or delete this file, then rerun normalization."
            )

        backup_path = normalized_dir.with_name(f"{normalized_dir.name}.legacy.gpkg")
        if backup_path.exists():
            raise RuntimeError(
                "Cannot migrate legacy normalized artifact because backup path already exists: "
                f"{backup_path}. Move/delete conflicting files and rerun."
            )

        normalized_dir.replace(backup_path)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        migrated_target = normalized_dir / f"{dataset_name}.gpkg"
        if not migrated_target.exists():
            backup_path.replace(migrated_target)
            _emit(progress_callback, "normalize", f"Migrated legacy normalized file into bundle: {migrated_target.name}")
        else:
            # Keep backup when a canonical target already exists.
            _emit(progress_callback, "normalize", f"Legacy normalized file kept as backup: {backup_path.name}")
        return

    normalized_dir.mkdir(parents=True, exist_ok=True)


def _publish_normalized_gpkg(partial_gpkg: Path, gpkg_path: Path) -> None:
    """Publish a validated GPKG and tolerate delayed bind-mount metadata updates.

    Docker Desktop bind mounts backed by Windows filesystems can briefly expose
    stale entry metadata immediately after rename/replace.  Treat those transient
    states as retryable and only accept the publication once the destination is a
    non-empty SQLite file.
    """
    if not partial_gpkg.exists() or partial_gpkg.stat().st_size <= 0:
        raise RuntimeError(f"Normalized temporary GPKG is missing or empty: {partial_gpkg}")
    if not _looks_like_sqlite(partial_gpkg):
        raise RuntimeError(f"Normalized temporary GPKG is not a SQLite file: {partial_gpkg}")

    _prepare_gpkg_target_slot(gpkg_path)
    partial_gpkg.replace(gpkg_path)

    deadline = time.monotonic() + 15.0
    last_state = "not checked"
    while time.monotonic() < deadline:
        try:
            if gpkg_path.exists():
                if gpkg_path.is_file():
                    size = gpkg_path.stat().st_size
                    if size > 0 and _looks_like_sqlite(gpkg_path):
                        return
                    last_state = f"file(size={size}, sqlite={_looks_like_sqlite(gpkg_path)})"
                elif gpkg_path.is_dir():
                    children = sorted(gpkg_path.iterdir(), key=lambda item: item.name)
                    if not children and partial_gpkg.exists():
                        # If another process recreated the target path as an empty
                        # directory before publish became visible, recover in-place.
                        gpkg_path.rmdir()
                        partial_gpkg.replace(gpkg_path)
                        last_state = "directory(empty)->replaced"
                        continue
                    if children:
                        preview = ", ".join(child.name for child in children[:5])
                        if len(children) > 5:
                            preview += f", ... {len(children) - 5} more"
                        last_state = f"directory(children={preview})"
                    else:
                        last_state = "directory(empty)"
                else:
                    last_state = "other filesystem entry"
            else:
                last_state = "missing"
        except OSError as exc:
            last_state = f"filesystem error: {exc!r}"
        time.sleep(0.1)

    # A replace can occasionally become visible later on a bind mount.  If the
    # source still exists and the destination is truly absent, retry once, then
    # use the same SQLite-aware verification window.
    if partial_gpkg.exists() and (not gpkg_path.exists() or (gpkg_path.exists() and gpkg_path.is_dir())):
        if gpkg_path.exists() and gpkg_path.is_dir():
            _prepare_gpkg_target_slot(gpkg_path)
        partial_gpkg.replace(gpkg_path)
        retry_deadline = time.monotonic() + 5.0
        while time.monotonic() < retry_deadline:
            try:
                if (
                    gpkg_path.exists()
                    and gpkg_path.is_file()
                    and gpkg_path.stat().st_size > 0
                    and _looks_like_sqlite(gpkg_path)
                ):
                    return
            except OSError:
                pass
            time.sleep(0.1)

    raise RuntimeError(
        "Normalized GPKG was validated but could not be published: "
        f"{partial_gpkg} -> {gpkg_path}. Last observed target state: {last_state}. "
        f"Directory contents: {_directory_snapshot(gpkg_path.parent)}"
    )


def normalize_source_to_gpkg(
    *,
    dataset_name: str,
    source_path: str | Path,
    normalized_dir: str | Path,
    source_format: str,
    profile_plan: Mapping[str, Any],
    bounds: str | list[float] | tuple[float, ...] | None,
    normalized_crs: str = DEFAULT_NORMALIZED_CRS,
    progress_callback: ProgressCallback | None = None,
    run_command: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Normalize a raw vector source into a cached canonical GPKG plus manifest."""
    source_path = Path(source_path)
    normalized_dir = Path(normalized_dir)
    _ensure_normalized_dir(
        normalized_dir=normalized_dir,
        dataset_name=dataset_name,
        progress_callback=progress_callback,
    )

    with _stage_a_dataset_lock(
        normalized_dir=normalized_dir,
        dataset_name=dataset_name,
        progress_callback=progress_callback,
    ):
        gpkg_path = normalized_dir / f"{dataset_name}.gpkg"
        _prepare_gpkg_target_slot(gpkg_path)
        manifest_path = _manifest_path_for(gpkg_path)
        partial_gpkg = gpkg_path.with_suffix(".partial.gpkg")
        partial_manifest = manifest_path.with_name(manifest_path.name + ".partial")

        gdal_version = _gdal_version()
        source_sha = sha256_file(source_path)
        fingerprint = normalization_fingerprint(
            source_sha256=source_sha,
            profile_plan=profile_plan,
            bounds=bounds,
            normalized_crs=normalized_crs,
            gdal_version=gdal_version,
        )

        existing_manifest = _load_manifest(manifest_path)
        if (
            gpkg_path.exists()
            and gpkg_path.stat().st_size > 0
            and existing_manifest
            and existing_manifest.get("fingerprint") == fingerprint
            and existing_manifest.get("gpkg_sha256")
        ):
            validation = validate_normalized_gpkg(
                gpkg_path,
                manifest=existing_manifest,
                expected_crs=str(normalized_crs or DEFAULT_NORMALIZED_CRS),
            )
            _emit(progress_callback, "normalize", f"Reusing normalized GPKG: {gpkg_path.name}")
            return {
                "path": gpkg_path,
                "manifest_path": manifest_path,
                "manifest": existing_manifest,
                "validation": validation,
                "artifact_status": "reused_from_cache",
            }

        partial_gpkg.unlink(missing_ok=True)
        partial_manifest.unlink(missing_ok=True)
        _emit(progress_callback, "normalize", f"Normalizing source to canonical GPKG: {gpkg_path.name}")

        normalization_rules = dict((profile_plan or {}).get("normalization") or {})
        make_valid = bool(normalization_rules.get("make_valid", False))
        cmd = build_normalization_command(
            source_path=source_path,
            output_path=partial_gpkg,
            bounds=bounds,
            normalized_crs=normalized_crs,
            make_valid=make_valid,
        )
        started = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        runner = run_command
        if runner is None:
            completed = subprocess.run(cmd, capture_output=True, text=True)
            exit_code = completed.returncode
            combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        else:
            result = runner(cmd)
            exit_code = int(result.get("exit_code", 0))
            combined_output = str(result.get("combined_output") or "")

        elapsed = time.perf_counter() - started
        if exit_code != 0:
            raise RuntimeError(
                "Normalization failed "
                f"(exit {exit_code}) for {source_path} -> {partial_gpkg}:\n{combined_output[-8000:]}"
            )

        validation = validate_normalized_gpkg(
            partial_gpkg,
            expected_crs=str(normalized_crs or DEFAULT_NORMALIZED_CRS),
        )
        gpkg_sha = sha256_file(partial_gpkg)

        normalized_layers = validation.get("layers") or []
        manifest = {
            "schema_version": NORMALIZATION_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": started_at,
            "normalization_time_ms": round(elapsed * 1000),
            "source_filename": source_path.name,
            "source_type": source_format,
            "source_sha256": source_sha,
            "source_size": source_path.stat().st_size,
            "fingerprint": fingerprint,
            "normalization_rules_hash": fingerprint["normalization_rules_hash"],
            "bounds": _parse_bounds(bounds) or [],
            "source_crs": "source",
            "normalized_crs": str(normalized_crs or DEFAULT_NORMALIZED_CRS),
            "clip_to_bounds": bool(_parse_bounds(bounds)),
            "make_valid": make_valid,
            "source_layers": [layer.get("name") for layer in normalized_layers],
            "normalized_layers": normalized_layers,
            "layer_counts": {
                layer.get("name"): {"written": layer.get("feature_count"), "source": layer.get("feature_count")}
                for layer in normalized_layers
                if layer.get("name")
            },
            "unknown_feature_counts": [
                layer.get("name") for layer in normalized_layers if layer.get("feature_count") is None
            ],
            "dropped": [],
            "stable_id_strategy": (
                ((profile_plan.get("normalization") or {}).get("stable_feature_id_strategy"))
                or "source_id_or_composite_key_or_hash"
            ),
            "warnings": [],
            "gdal_version": gdal_version,
            "app_version": "local",
            "gpkg_sha256": gpkg_sha,
            "command": cmd,
        }

        _publish_normalized_gpkg(partial_gpkg, gpkg_path)
        _write_json_atomic(manifest_path, manifest)
        validation = validate_normalized_gpkg(gpkg_path, manifest=manifest, expected_crs=str(normalized_crs or DEFAULT_NORMALIZED_CRS))
        _emit(progress_callback, "normalize", f"Normalized GPKG ready: {gpkg_path.name}")

        return {
            "path": gpkg_path,
            "manifest_path": manifest_path,
            "manifest": manifest,
            "validation": validation,
            "artifact_status": "generated",
        }


def normalized_bundle_paths(gpkg_path: str | Path) -> list[Path]:
    gpkg = Path(gpkg_path)
    return [gpkg, _manifest_path_for(gpkg)]


def available_disk_bytes(path: str | Path) -> int:
    usage = shutil.disk_usage(Path(path))
    return int(usage.free)
