"""HTTP API for dataset import, status, and dataset management."""

import os
import sqlite3
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from .dataset_profile import build_dataset_profile, load_dataset_profile, profile_sha256, save_dataset_profile, validate_dataset_profile
from .config import load_config
from .convert import (
    ConversionCancelledError, dataset_name_from_url, resolve_dataset_name, run_conversion_pipeline,
)
from .protocol_summary import synthesize_protocol_v2
from .pmtiles_extent import archive_extent
from .protocol import list_protocols, load_protocol
from .profile_rules import derive_profile_plan
from .analyzer import analyze_source, get_source_format

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 4 GB

DATA_DIR = Path("/data")
PROTOCOLS_DIR = DATA_DIR / "protocols"
OUTPUT_DIR = DATA_DIR / "output"
SOURCES_DIR = DATA_DIR / "sources"
NORMALIZED_DIR = DATA_DIR / "normalized"
PROFILES_DIR = DATA_DIR / "profiles" / "datasets"

_jobs = {}
_jobs_lock = threading.Lock()
JOB_PROGRESS_LIMIT = 120

# Only one conversion runs at a time. conversion_time_ms and peak_memory_mb are
# reported results, so two conversions contending for CPU and memory would
# corrupt both datasets' numbers. Imports queue instead of running in parallel.
_conversion_lock = threading.Lock()


@contextmanager
def conversion_slot():
    """Hold the single conversion slot for the duration of the block."""
    _conversion_lock.acquire()
    try:
        yield
    finally:
        _conversion_lock.release()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _serialize_job(job):
    return {
        "name": job["name"],
        "url": job["url"],
        "pipeline_mode": job.get("pipeline_mode", "full"),
        "status": job["status"],
        "stage": job.get("stage"),
        "progress": job.get("progress", []),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "error": job.get("error"),
        "cancel_requested": bool(job.get("cancel_requested", False)),
    }


def _protocol_path(name):
    return PROTOCOLS_DIR / f"{name}.json"


def _profile_path(name):
    return PROFILES_DIR / f"{name}.yaml"


def _normalized_paths(name):
    base = NORMALIZED_DIR / name
    return {
        "gpkg": base / f"{name}.gpkg",
        "manifest": base / f"{name}.normalization.json",
    }


def _load_legacy_protocol(name):
    protocol_path = _protocol_path(name)
    if not protocol_path.exists():
        return None
    return load_protocol(protocol_path)


def _ensure_profile(name, legacy_protocol=None, regenerate=False):
    profile_path = _profile_path(name)
    if profile_path.exists() and not regenerate:
        profile = load_dataset_profile(profile_path)
        validate_dataset_profile(profile)
        return profile, profile_path, "saved"

    legacy_protocol = legacy_protocol or _load_legacy_protocol(name) or {}
    analysis = {"layers": legacy_protocol.get("layers") or []}
    profile_plan = derive_profile_plan(
        dataset_name=name,
        source_path=legacy_protocol.get("dataset", {}).get("url") or name,
        source_format=legacy_protocol.get("dataset", {}).get("format") or "unknown",
        analysis=analysis,
    )
    draft = build_dataset_profile(
        name,
        legacy_protocol.get("dataset", {}).get("url") or name,
        legacy_protocol.get("dataset", {}).get("format") or "unknown",
        analysis,
        profile_plan=profile_plan,
    )
    validate_dataset_profile(draft)
    save_dataset_profile(draft, PROFILES_DIR)
    return draft, profile_path, "auto_generated"


def _with_data_extent(protocol):
    """Fill dataset.extent from the archive's own tile directory when nothing else supplied one.

    A conversion that was not given an extent writes the whole world and a (0, 0) center into the archive header, so a viewer that trusts
    the header opens on empty ocean (the Netherlands archives did). The tile directory lists exactly which tiles exist. An extent that
    is already there (from the profile's output bounds) is left alone.
    """
    dataset = protocol.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("extent"):
        return protocol
    for fmt in ("mlt", "mvt"):
        filename = ((protocol.get("outputs") or {}).get(fmt) or {}).get("path")
        extent = archive_extent(OUTPUT_DIR / Path(filename).name) if filename else None
        if extent:
            dataset["extent"] = extent
            dataset["extent_source"] = "tile directory"
            break
    return protocol


def _v2_protocol(name, legacy_protocol=None, regenerate_profile=False):
    legacy_protocol = legacy_protocol or _load_legacy_protocol(name)
    if legacy_protocol is None:
        return None
    return _with_data_extent(synthesize_protocol_v2(legacy_protocol))


def _v2_protocols():
    protocols = []
    for path in reversed(list_protocols(PROTOCOLS_DIR)):
        try:
            legacy = load_protocol(path)
            protocols.append(_with_data_extent(synthesize_protocol_v2(legacy)))
        except Exception:
            continue
    return protocols


def _get_job(name):
    with _jobs_lock:
        return dict(_jobs[name]) if name in _jobs else None


def _store_job(job):
    with _jobs_lock:
        _jobs[job["name"]] = dict(job)


def _update_job(name, **updates):
    with _jobs_lock:
        if name not in _jobs:
            return
        _jobs[name].update(updates)
        _jobs[name]["updated_at"] = _now_iso()


def _delete_job(name):
    with _jobs_lock:
        _jobs.pop(name, None)


def _append_job_progress(name, stage, message):
    with _jobs_lock:
        if name not in _jobs:
            return
        progress = _jobs[name].setdefault("progress", [])
        progress.append({
            "timestamp": _now_iso(),
            "stage": stage,
            "message": message,
        })
        if len(progress) > JOB_PROGRESS_LIMIT:
            del progress[:-JOB_PROGRESS_LIMIT]
        _jobs[name]["stage"] = stage
        _jobs[name]["updated_at"] = _now_iso()


def _load_protocols():
    return _v2_protocols()


def _list_normalized_bundles():
    bundles = []
    if not NORMALIZED_DIR.exists():
        return bundles
    for entry in sorted(NORMALIZED_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        name = entry.name
        gpkg = entry / f"{name}.gpkg"
        manifest = entry / f"{name}.normalization.json"
        bundles.append({
            "name": name,
            "gpkg_path": str(gpkg),
            "gpkg_exists": gpkg.exists(),
            "gpkg_size_bytes": gpkg.stat().st_size if gpkg.exists() else None,
            "manifest_path": str(manifest),
            "manifest_exists": manifest.exists(),
            "has_protocol": _protocol_path(name).exists(),
        })
    return bundles


def _infer_source_format_from_text(source_text):
    token = str(source_text or "").strip().lower()
    if token.endswith(".osm.pbf") or token.endswith(".pbf"):
        return "osm.pbf"
    if token.endswith(".gpkg"):
        return "gpkg"
    if token.endswith(".geojson") or token.endswith(".json"):
        return "geojson"
    if token.endswith(".shp"):
        return "shp"
    if token.endswith(".parquet") or token.endswith(".geoparquet"):
        return "parquet"
    if token.endswith(".gdb"):
        return "gdb"
    if token.endswith(".csv") or token.endswith(".tsv"):
        return "csv"
    if token.endswith(".gml"):
        return "citygml"
    if token.endswith(".tif") or token.endswith(".tiff"):
        return "tif"
    if token.endswith(".zip"):
        return "unknown"
    return "unknown"


def _preview_plan_from_payload(payload):
    name_override = (payload.get("name") or "").strip() if isinstance(payload, dict) else ""
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    file_path = (payload.get("file_path") or "").strip() if isinstance(payload, dict) else ""
    filename = (payload.get("filename") or "").strip() if isinstance(payload, dict) else ""

    if not (url or file_path or filename):
        raise ValueError("Provide one of: url, file_path, or filename.")

    source_ref = ""
    source_format = "unknown"
    analysis = {"layers": []}

    if file_path:
        source_path = Path(file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not source_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        source_ref = str(source_path)
        source_format = get_source_format(source_path)
        if source_format not in {"osm.pbf", "tif", "unknown"}:
            try:
                analysis = analyze_source(source_path)
            except Exception:
                analysis = {"layers": []}
    elif url:
        source_ref = url
        source_format = _infer_source_format_from_text(urlparse(url).path or url)
    else:
        source_ref = filename
        source_format = _infer_source_format_from_text(filename)

    dataset_name = resolve_dataset_name(source_ref, name_override or None)
    cfg = load_config(_CONFIG_PATH if _CONFIG_PATH.exists() else None)
    profile_plan = derive_profile_plan(
        dataset_name=dataset_name,
        source_path=source_ref,
        source_format=source_format,
        analysis=analysis,
        rules_path=cfg.get("profile_rules_path"),
    )

    return {
        "dataset_name": dataset_name,
        "source_ref": source_ref,
        "source_format": source_format,
        "analysis_layer_count": len((analysis or {}).get("layers") or []),
        "plan": profile_plan,
    }


def _remove_dataset_files(name):
    deleted = False
    protocol_path = _protocol_path(name)
    if protocol_path.exists():
        protocol_path.unlink()
        deleted = True

    profile_path = _profile_path(name)
    if profile_path.exists():
        profile_path.unlink()
        deleted = True

    for path in OUTPUT_DIR.glob(f"{name}_*"):
        if path.is_file():
            path.unlink()
            deleted = True

    source_dir = SOURCES_DIR / name
    if source_dir.exists():
        for path in source_dir.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(source_dir.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        source_dir.rmdir()
        deleted = True

    normalized_dir = NORMALIZED_DIR / name
    if normalized_dir.exists():
        for path in normalized_dir.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(normalized_dir.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        normalized_dir.rmdir()
        deleted = True

    return deleted


def _tail_error_log(log_file, line_count=80, char_limit=8000):
    """Read a concise tail of a conversion log for failed-job diagnostics."""
    if not log_file:
        return ""
    path = DATA_DIR / "logs" / str(log_file)
    if not path.exists() or not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    tail = "\n".join(lines[-line_count:])
    if len(tail) > char_limit:
        tail = tail[-char_limit:]
    return tail


def _build_failure_report(conversions):
    failed = []
    for key, data in (conversions or {}).items():
        if (data.get("exit_code") or 0) == 0:
            continue
        log_file = data.get("log_file")
        error_message = (data.get("error_message") or "").strip()
        if not error_message:
            error_message = _tail_error_log(log_file)
        header = f"[{key}] exit_code={data.get('exit_code')}"
        if log_file:
            header += f"\nlog: /data/logs/{log_file}"
        if error_message:
            failed.append(f"{header}\n{error_message}")
        else:
            failed.append(f"{header}\nConversion failed without captured stderr tail")
    return "\n\n".join(failed)


def _local_source_missing(url):
    """True when `url` is a local path that no longer exists, so a rerun cannot start from it.

    Remote sources (http, https, ...) are fetched again by the downloader, so they are never "missing" here. Sources were once deleted
    unconditionally after conversion, so datasets converted back then have a path in their profile but no file behind it.
    """
    if not url:
        return True
    if url.startswith("upload://"):
        return True                                   # an uploaded file is not kept anywhere a rerun could find it
    path = url[len("local://"):] if url.startswith("local://") else url
    if "://" in path:
        return False
    return not Path(path).exists()


def _snapshot_files(paths):
    """Remember what files held before a rerun: path -> bytes, or None for a file that did not exist."""
    return {p: (p.read_bytes() if p.exists() else None) for p in paths}


def _restore_files(snapshot):
    for path, content in snapshot.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(content)


def _run_import_job(name, url, cancel_event, keep_existing=False, pipeline_mode="full"):
    def progress_callback(stage, message):
        _append_job_progress(name, stage, message)
        if cancel_event.is_set():
            raise ConversionCancelledError(f"Import cancelled by user: {name}")

    # keep_existing (a rerun): the dataset's protocol and profile are what the viewer reads, and the pipeline rewrites them even when a
    # conversion fails. Snapshot them as the conversion starts and put them back unless the job completes, so a failed or cancelled rerun
    # leaves the current map exactly as it was. New archives are written beside the old ones, never over them.
    snapshot = None
    completed = False
    _append_job_progress(name, "queued", f"Job queued for {name}")
    if cancel_event.is_set():
        _update_job(name, status="canceled", stage="canceled", error="Cancelled by user")
        _append_job_progress(name, "canceled", "Cancelled before conversion started")
        return
    try:
        # Wait for the conversion slot rather than running alongside another
        # dataset: contended CPU and memory would corrupt the timing and
        # memory metrics of both.
        with conversion_slot():
            if cancel_event.is_set():
                _update_job(name, status="canceled", stage="canceled", error="Cancelled by user")
                _append_job_progress(name, "canceled", "Cancelled before conversion started")
                return
            _update_job(name, status="running", error=None)
            if keep_existing:
                snapshot = _snapshot_files([_protocol_path(name), _profile_path(name)])
            progress_callback("start", f"Starting conversion for {name}")
            result = run_conversion_pipeline(
                name=name,
                url=url,
                config_path=str(_CONFIG_PATH),
                progress_callback=progress_callback,
                cancel_event=cancel_event,
                pipeline_mode=pipeline_mode,
            )
        status = result.get("status", "failed")
        if status == "completed":
            completed = True
            done_msg = "All conversions completed successfully"
            if pipeline_mode == "stage_a":
                done_msg = "Stage A normalization completed"
            elif pipeline_mode == "stage_b":
                done_msg = "Stage B generation completed"
            progress_callback("done", done_msg)
            _update_job(name, status="completed", stage="done", error=None)
        elif status == "canceled":
            _append_job_progress(name, "canceled", "Cancelled by user")
            _update_job(name, status="canceled", stage="canceled", error="Cancelled by user")
        else:
            failure_report = _build_failure_report(result.get("conversions", {}))
            progress_callback("failed", "One or more conversions failed")
            _update_job(
                name,
                status="failed",
                stage="failed",
                error=failure_report or "Conversion failed",
            )
    except ConversionCancelledError:
        _append_job_progress(name, "canceled", "Cancelled by user")
        _update_job(name, status="canceled", stage="canceled", error="Cancelled by user")
    except Exception as exc:
        _append_job_progress(name, "failed", str(exc))
        _update_job(name, status="failed", stage="failed", error=f"{exc}\n{traceback.format_exc(limit=5)}")
    finally:
        if snapshot is not None and not completed:
            _restore_files(snapshot)
            _append_job_progress(name, "restored", "Rerun did not complete: the previous version of the map was kept")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/datasets")
def list_datasets():
    jobs = []
    with _jobs_lock:
        jobs = [_serialize_job(job) for job in _jobs.values()]
    jobs.sort(key=lambda item: item["created_at"], reverse=True)
    return jsonify({
        "datasets": _load_protocols(),
        "normalized": _list_normalized_bundles(),
        "jobs": jobs,
    })


@app.get("/api/datasets/<name>")
def get_dataset(name):
    protocol = _v2_protocol(name)
    if protocol is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    return jsonify(protocol)


@app.get("/api/datasets/<name>/profile")
def get_dataset_profile(name):
    legacy = _load_legacy_protocol(name)
    if legacy is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    profile, profile_path, origin = _ensure_profile(name, legacy)
    return jsonify({"profile": profile, "path": str(profile_path), "origin": origin, "sha256": profile_sha256(profile_path)})


@app.put("/api/datasets/<name>/profile")
def put_dataset_profile(name):
    payload = request.get_json(silent=True) or {}
    profile = payload.get("profile") if isinstance(payload, dict) else None
    if not isinstance(profile, dict):
        return jsonify({"error": "Field 'profile' is required and must be an object."}), 400
    try:
        validate_dataset_profile(profile)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = save_dataset_profile(profile, PROFILES_DIR)
    return jsonify({"saved": True, "path": str(path), "sha256": profile_sha256(path)})


@app.post("/api/datasets/<name>/profile/regenerate")
def regenerate_dataset_profile(name):
    legacy = _load_legacy_protocol(name)
    if legacy is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    analysis = {"layers": legacy.get("layers") or []}
    profile_plan = derive_profile_plan(
        dataset_name=name,
        source_path=legacy.get("dataset", {}).get("url") or name,
        source_format=legacy.get("dataset", {}).get("format") or "unknown",
        analysis=analysis,
    )
    profile = build_dataset_profile(
        name,
        legacy.get("dataset", {}).get("url") or name,
        legacy.get("dataset", {}).get("format") or "unknown",
        analysis,
        profile_plan=profile_plan,
    )
    validate_dataset_profile(profile)
    path = save_dataset_profile(profile, PROFILES_DIR)
    return jsonify({"profile": profile, "path": str(path), "sha256": profile_sha256(path), "origin": "auto_generated"})


@app.get("/api/datasets/<name>/structure")
def get_dataset_structure(name):
    protocol = _v2_protocol(name)
    if protocol is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    return jsonify({
        "dataset": protocol["dataset"],
        "profile": protocol["profile"],
        "topology": protocol["topology"],
        "outputs": protocol["outputs"],
        "zoom_summary": protocol["zoom_summary"],
        "layer_summary": protocol["layer_summary"],
    })


@app.get("/api/datasets/<name>/workloads")
def get_dataset_workloads(name):
    protocol = _v2_protocol(name)
    if protocol is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    return jsonify({"workload_summary": protocol["workload_summary"]})


@app.get("/api/datasets/<name>/validation")
def get_dataset_validation(name):
    protocol = _v2_protocol(name)
    if protocol is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    return jsonify(protocol["validation"])


@app.get("/api/datasets/<name>/normalized")
def get_dataset_normalized(name):
    paths = _normalized_paths(name)
    manifest = None
    if paths["manifest"].exists():
        try:
            import json
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        except Exception:
            manifest = None
    return jsonify({
        "dataset": name,
        "gpkg": {
            "path": str(paths["gpkg"]),
            "exists": paths["gpkg"].exists(),
            "size_bytes": paths["gpkg"].stat().st_size if paths["gpkg"].exists() else None,
        },
        "manifest": {
            "path": str(paths["manifest"]),
            "exists": paths["manifest"].exists(),
            "size_bytes": paths["manifest"].stat().st_size if paths["manifest"].exists() else None,
            "data": manifest,
        },
    })


@app.get("/api/datasets/<name>/normalized/gpkg")
def download_normalized_gpkg(name):
    path = _normalized_paths(name)["gpkg"]
    if not path.exists() or not path.is_file():
        return jsonify({"error": f"Normalized GPKG not found for dataset '{name}'."}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.get("/api/datasets/<name>/normalized/manifest")
def download_normalization_manifest(name):
    path = _normalized_paths(name)["manifest"]
    if not path.exists() or not path.is_file():
        return jsonify({"error": f"Normalization manifest not found for dataset '{name}'."}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.post("/api/datasets/<name>/reconvert")
def reconvert_dataset(name):
    protocol = _load_legacy_protocol(name)
    if protocol is None:
        return jsonify({"error": f"Dataset not found: {name}"}), 404
    profile_path = _profile_path(name)
    if profile_path.exists():
        profile = load_dataset_profile(profile_path)
        url = (profile.get("dataset") or {}).get("source_path") or (profile.get("dataset") or {}).get("id")
    else:
        url = (protocol.get("dataset") or {}).get("source_path") or (protocol.get("dataset") or {}).get("url")
    if not url:
        return jsonify({"error": f"Dataset '{name}' has no source URL to reconvert from."}), 400
    if _local_source_missing(url):
        return jsonify({"error": (
            f"The source file for '{name}' is missing: {url}. Put it back there, or import it again with the Process form, "
            "then rerun. The current map has not been touched."
        )}), 400
    if _get_job(name) and _get_job(name)["status"] in {"queued", "running", "canceling"}:
        return jsonify({"error": f"Dataset '{name}' is already being processed."}), 409

    job = {
        "name": name,
        "url": url,
        "pipeline_mode": "full",
        "status": "queued",
        "stage": "queued",
        "progress": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
        "cancel_requested": False,
        "cancel_event": threading.Event(),
    }
    _store_job(job)

    worker = threading.Thread(target=_run_import_job, args=(name, url, job["cancel_event"], True, "full"), daemon=True)
    worker.start()
    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/datasets/import")
def import_dataset():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Field 'url' is required."}), 400

    # A study import states its name: two of the four datasets derive one the
    # paper never uses -- the Groundswell collection URL gives "granules", and
    # the canonical Saentis URL gives a name matching none of the recorded
    # figures. Omitted, the derivation stands, so UI imports are unaffected.
    name = resolve_dataset_name(url, payload.get("name"))
    existing_job = _get_job(name)
    if existing_job and existing_job["status"] in {"queued", "running", "canceling"}:
        return jsonify({"error": f"Dataset '{name}' is already being processed."}), 409
    if _protocol_path(name).exists():
        return jsonify({"error": f"Dataset '{name}' already exists."}), 409

    job = {
        "name": name,
        "url": url,
        "pipeline_mode": "full",
        "status": "queued",
        "stage": "queued",
        "progress": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
        "cancel_requested": False,
        "cancel_event": threading.Event(),
    }
    _store_job(job)

    worker = threading.Thread(target=_run_import_job, args=(name, url, job["cancel_event"], False, "full"), daemon=True)
    worker.start()

    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/datasets/upload")
def upload_dataset():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename in upload."}), 400

    filename = secure_filename(file.filename)
    name = dataset_name_from_url(filename)

    existing_job = _get_job(name)
    if existing_job and existing_job["status"] in {"queued", "running", "canceling"}:
        return jsonify({"error": f"Dataset '{name}' is already being processed."}), 409
    if _protocol_path(name).exists():
        return jsonify({"error": f"Dataset '{name}' already exists."}), 409

    dest_dir = SOURCES_DIR / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    file.save(str(dest_path))

    job = {
        "name": name,
        "url": f"upload://{filename}",
        "pipeline_mode": "full",
        "status": "queued",
        "stage": "queued",
        "progress": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
        "cancel_requested": False,
        "cancel_event": threading.Event(),
    }
    _store_job(job)

    worker = threading.Thread(target=_run_import_job, args=(name, str(dest_path), job["cancel_event"], False, "full"), daemon=True)
    worker.start()

    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/datasets/local-file")
def process_local_file():
    """Process a file from a local server path (no upload needed)."""
    payload = request.get_json(silent=True) or {}
    file_path = (payload.get("file_path") or "").strip()
    if not file_path:
        return jsonify({"error": "Field 'file_path' is required."}), 400

    # Validate the file exists and is readable
    path = Path(file_path)
    if not path.exists():
        return jsonify({"error": f"File not found: {file_path}"}), 404
    if not path.is_file():
        return jsonify({"error": f"Path is not a file: {file_path}"}), 400

    # Create dataset name from filename, unless the caller names it.
    name = resolve_dataset_name(path.name, payload.get("name"))

    existing_job = _get_job(name)
    if existing_job and existing_job["status"] in {"queued", "running", "canceling"}:
        return jsonify({"error": f"Dataset '{name}' is already being processed."}), 409
    if _protocol_path(name).exists():
        return jsonify({"error": f"Dataset '{name}' already exists."}), 409

    job = {
        "name": name,
        "url": f"local://{file_path}",
        "pipeline_mode": "full",
        "status": "queued",
        "stage": "queued",
        "progress": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
        "cancel_requested": False,
        "cancel_event": threading.Event(),
    }
    _store_job(job)

    worker = threading.Thread(target=_run_import_job, args=(name, str(path), job["cancel_event"], False, "full"), daemon=True)
    worker.start()

    return jsonify({"job": _serialize_job(job)}), 202


def _queue_stage_job(name, url, *, pipeline_mode):
    existing_job = _get_job(name)
    if existing_job and existing_job["status"] in {"queued", "running", "canceling"}:
        return None, (jsonify({"error": f"Dataset '{name}' is already being processed."}), 409)

    job = {
        "name": name,
        "url": url,
        "pipeline_mode": pipeline_mode,
        "status": "queued",
        "stage": "queued",
        "progress": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None,
        "cancel_requested": False,
        "cancel_event": threading.Event(),
    }
    _store_job(job)
    worker = threading.Thread(
        target=_run_import_job,
        args=(name, url, job["cancel_event"], False, pipeline_mode),
        daemon=True,
    )
    worker.start()
    return job, None


@app.post("/api/stage-a/import")
def stage_a_import():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Field 'url' is required."}), 400
    name = resolve_dataset_name(url, payload.get("name"))
    job, error = _queue_stage_job(name, url, pipeline_mode="stage_a")
    if error:
        return error
    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/stage-a/local-file")
def stage_a_local_file():
    payload = request.get_json(silent=True) or {}
    file_path = (payload.get("file_path") or "").strip()
    if not file_path:
        return jsonify({"error": "Field 'file_path' is required."}), 400
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return jsonify({"error": f"File not found: {file_path}"}), 404
    name = resolve_dataset_name(path.name, payload.get("name"))
    job, error = _queue_stage_job(name, str(path), pipeline_mode="stage_a")
    if error:
        return error
    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/stage-a/upload")
def stage_a_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename in upload."}), 400

    filename = secure_filename(file.filename)
    name = dataset_name_from_url(filename)
    dest_dir = SOURCES_DIR / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    file.save(str(dest_path))

    job, error = _queue_stage_job(name, str(dest_path), pipeline_mode="stage_a")
    if error:
        return error
    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/stage-b/generate")
def stage_b_generate():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    gpkg_path = (payload.get("gpkg_path") or "").strip()
    if not name:
        return jsonify({"error": "Field 'name' is required."}), 400
    if not gpkg_path:
        gpkg_path = str(_normalized_paths(name)["gpkg"])
    gpkg = Path(gpkg_path)
    if not gpkg.exists() or not gpkg.is_file():
        return jsonify({"error": f"Normalized GPKG not found: {gpkg_path}"}), 404

    job, error = _queue_stage_job(name, str(gpkg), pipeline_mode="stage_b")
    if error:
        return error
    return jsonify({"job": _serialize_job(job)}), 202


@app.post("/api/jobs/<name>/cancel")
def cancel_job(name):
    with _jobs_lock:
        job = _jobs.get(name)
        if job is None:
            return jsonify({"error": f"Job not found: {name}"}), 404

        status = str(job.get("status") or "")
        if status in {"completed", "failed", "canceled"}:
            return jsonify({"job": _serialize_job(job), "changed": False})

        job["cancel_requested"] = True
        cancel_event = job.get("cancel_event")
        if cancel_event is not None:
            cancel_event.set()

        if status == "queued":
            job["status"] = "canceled"
            job["stage"] = "canceled"
            job["error"] = "Cancelled by user"
            progress = job.setdefault("progress", [])
            progress.append({
                "timestamp": _now_iso(),
                "stage": "canceled",
                "message": "Cancelled before conversion started",
            })
        elif status in {"running", "canceling"}:
            job["status"] = "canceling"
            job["stage"] = "canceling"
            progress = job.setdefault("progress", [])
            progress.append({
                "timestamp": _now_iso(),
                "stage": "canceling",
                "message": "Cancellation requested, stopping active conversion...",
            })

        if len(job.get("progress", [])) > JOB_PROGRESS_LIMIT:
            del job["progress"][:-JOB_PROGRESS_LIMIT]
        job["updated_at"] = _now_iso()

        return jsonify({"job": _serialize_job(job), "changed": True})


@app.post("/api/profile-plan/preview")
def preview_profile_plan():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(_preview_plan_from_payload(payload))
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


_tile_db_local = threading.local()


def tile_db_connection(path):
    """Return a per-thread, read-only SQLite connection for an MBTiles archive.

    Connections are cached rather than opened per request: MBTiles is measured
    against PMTiles, which Caddy serves as a static file, so a connect-and-open
    on every tile would show up in the results as if it were a cost of the
    container format rather than of this server.
    """
    key = str(path)
    cache = getattr(_tile_db_local, "connections", None)
    if cache is None:
        cache = _tile_db_local.connections = {}
    conn = cache.get(key)
    if conn is None:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        cache[key] = conn
    return conn


@app.get("/api/tiles/<name>/<fmt>/<int:z>/<int:x>/<int:y>")
def serve_tile(name, fmt, z, x, y):
    if fmt not in ("mvt", "mlt"):
        return "", 400
    path = OUTPUT_DIR / f"{name}_{fmt}.pmtiles"
    if not path.exists():
        return "", 404

    # PMTiles are served statically by the web tier; this handler stays for
    # compatibility with older clients during migration.
    return "", 204

    tile_data = b""
    content_type = "application/x-protobuf" if fmt == "mvt" else "application/x-mlt-tile"
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Timing-Allow-Origin": "*",
        # The benchmark reports tile bytes *transferred*, and fetch inflates a
        # gzipped body before it can be measured. Content-Length is what was
        # sent, so it has to stay readable even from another origin.
        "Access-Control-Expose-Headers": "Content-Length",
        "Content-Type": content_type,
        "Cache-Control": "no-store",
    }
    if tile_data[:2] == b"\x1f\x8b":
        headers["Content-Encoding"] = "gzip"
    return tile_data, 200, headers


@app.delete("/api/datasets/<name>")
def delete_dataset(name):
    existing_job = _get_job(name)
    if existing_job and existing_job["status"] in {"queued", "running", "canceling"}:
        return jsonify({"error": f"Dataset '{name}' is still being processed."}), 409

    deleted = _remove_dataset_files(name)
    if not deleted:
        return jsonify({"error": f"Dataset not found: {name}"}), 404

    _delete_job(name)
    return jsonify({"deleted": True, "name": name})


_CONFIG_PATH = DATA_DIR / "settings.yaml"
_EDITABLE_KEYS = {
    "tmp_dir",
    "min_zoom",
    "max_zoom",
    "java_heap",
    "citygml_layer_timeout_seconds",
    "citygml_skip_timeout_layers",
    "citygml_fallback_source_srs",
}


@app.get("/api/settings")
def get_settings():
    cfg = load_config(_CONFIG_PATH if _CONFIG_PATH.exists() else None)
    return jsonify({k: cfg.get(k) for k in _EDITABLE_KEYS})


@app.patch("/api/settings")
def patch_settings():
    payload = request.get_json(silent=True) or {}
    unknown = set(payload) - _EDITABLE_KEYS
    if unknown:
        return jsonify({"error": f"Unknown settings: {sorted(unknown)}"}), 400

    # Load current file content (preserve comments as much as possible)
    cfg_path = _CONFIG_PATH
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}
    else:
        current = {}

    current.update({k: v for k, v in payload.items()})

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(current, f, default_flow_style=False, allow_unicode=True)

    return jsonify(current)


def main():
    PROTOCOLS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("API_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
