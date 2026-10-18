"""Convert CityGML datasets to GeoPackage using ogr2ogr."""

import re
import sqlite3
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .ogr_append import append_attempts


class CityGMLConversionError(RuntimeError):
    """CityGML conversion failed, with diagnostics collected before failure."""

    def __init__(
        self,
        message,
        *,
        srs_diagnostics=None,
        tolerated_details=None,
        failed_details=None,
        unresolved_crs_layers=None,
    ):
        super().__init__(message)
        self.srs_diagnostics = list(srs_diagnostics or [])
        self.tolerated_details = dict(tolerated_details or {})
        self.failed_details = dict(failed_details or {})
        self.unresolved_crs_layers = list(unresolved_crs_layers or [])


def _collect_issue_lines(stderr_text):
    lines = []
    for raw in (stderr_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if any(token in low for token in ("error", "warning", "failed", "invalid", "skip")):
            lines.append(line)
    return lines


def _categorize_issue(line):
    low = line.lower()
    if "self-intersection" in low:
        return "self_intersection"
    if "non-closed" in low or "not closed" in low:
        return "ring_not_closed"
    if "topology" in low:
        return "topology_error"
    if "transform" in low or "projection" in low or "srs" in low or "crs" in low:
        return "crs_transform_error"
    if "invalid" in low and "geometry" in low:
        return "invalid_geometry"
    if "skip" in low:
        return "skipped_feature"
    if "warning" in low:
        return "warning"
    if "error" in low or "failed" in low:
        return "error"
    return "other"


def _summarize_stderr(stderr_text, *, sample_limit=8):
    issues = _collect_issue_lines(stderr_text)
    by_reason = {}
    for line in issues:
        reason = _categorize_issue(line)
        by_reason[reason] = by_reason.get(reason, 0) + 1
    top_reasons = sorted(by_reason.items(), key=lambda item: item[1], reverse=True)
    return {
        "issue_count": len(issues),
        "top_reasons": top_reasons,
        "samples": issues[:sample_limit],
    }


def _has_reason(summary, reason):
    if not summary:
        return False
    for name, _count in summary.get("top_reasons") or []:
        if name == reason:
            return True
    return False


def _extract_srs_from_file(path, max_bytes=131072):
    try:
        with open(path, "rb") as handle:
            blob = handle.read(max_bytes).decode("utf-8", "replace")
    except OSError:
        return None
    return srs_from_gml_header(blob)


def list_gml_members(zip_path):
    """Return every .gml entry in a zip archive, sorted by name.

    A CityGML archive is not necessarily one file: the Dutch BGT/IMGeo export
    ships one CityGML document per feature class, so all members matter.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        return sorted(n for n in zf.namelist() if n.lower().endswith(".gml"))


def layer_name_for_gml(gml_name):
    """Derive a tile-layer name from a GML member's filename."""
    stem = Path(gml_name.replace("\\", "/")).stem
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def srs_from_gml_header(blob):
    """Extract 'EPSG:<code>' from a GML srsName attribute, or None if absent.

    Handles both the URN form (urn:ogc:def:crs:EPSG::28992) and the OGC HTTP
    form (.../def/crs/EPSG/0/28992). Some BGT layers — bgt_pand.gml among them —
    declare no srsName at all, which is why callers need the None case.
    """
    match = re.search(r'srsName="([^"]+)"', blob)
    if not match:
        return None
    value = match.group(1)
    if "EPSG" not in value.upper():
        return None
    codes = re.findall(r"\d+", value)
    return f"EPSG:{codes[-1]}" if codes else None


def gml_sources_from_zip(zip_path):
    """Plan the conversion of every GML member of an archive.

    Returns [(member_name, layer_name, source_srs)], where source_srs is the
    CRS to force with -s_srs because that member declares none, or None when
    the member declares its own.

    Members are named, not resolved to /vsizip/ paths. GDAL's GML driver reads
    a document twice — once to infer the schema, once for the features — and a
    deflate stream cannot seek backwards, so reading in place re-inflates the
    member from its start on every pass. bgt_wegdeel.gml is 1.35 GB unpacked
    from 116 MB stored; in place it blew through the one-hour ogr2ogr timeout,
    while the same conversion from an extracted file takes 132 s. Callers
    extract each member before handing it to ogr2ogr.
    """
    zip_path = Path(zip_path)
    members = list_gml_members(zip_path)
    if not members:
        raise RuntimeError(f"No .gml files found in {zip_path}")

    declared = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in members:
            with zf.open(member) as handle:
                header = handle.read(131072).decode("utf-8", "replace")
            declared[member] = srs_from_gml_header(header)

    declared_unique = sorted({srs for srs in declared.values() if srs})
    fallback_srs = declared_unique[0] if len(declared_unique) == 1 else None
    return [
        (
            member,
            layer_name_for_gml(member),
            declared.get(member) or fallback_srs,
        )
        for member in members
    ]


def extract_member(zip_path, member, dest_dir):
    """Unpack one archive member into dest_dir and return its path.

    Members are unpacked one at a time rather than all at once: a city extract
    is 5.0 GB of GML unpacked from a 378 MB archive, which would sit on disk
    alongside the GeoPackage being assembled from it.
    """
    dest = Path(dest_dir) / Path(member.replace("\\", "/")).name
    with zipfile.ZipFile(zip_path, "r") as zf, zf.open(member) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    return dest




def layer_feature_counts(gpkg_path):
    """How many features each layer of a GeoPackage actually holds.

    Read straight from SQLite rather than through ogrinfo: this runs once over a
    finished file, and shelling out per member would cost 35 subprocesses on the
    Amsterdam extract.

    A member that ogr2ogr accepted without producing any features is the case
    this exists for. PDOK returns buurt, openbareruimte, stadsdeel, waterschap
    and wijk as 388-byte GML envelopes containing nothing; ogr2ogr exits 0 on
    each, so all 35 members look converted while only 30 layers arrive. Dropping
    an empty member is right -- not recording it means a member truncated by a
    failed download is indistinguishable from one that is legitimately empty.
    """
    counts = {}
    try:
        db = sqlite3.connect(f"file:{gpkg_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return counts
    try:
        names = [row[0] for row in db.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")]
        for name in names:
            try:
                counts[name] = db.execute(
                    f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.Error:
                counts[name] = 0
    except sqlite3.Error:
        return counts
    finally:
        db.close()
    return counts


def citygml_to_gpkg(
    source_path,
    output_path,
    progress_callback=None,
    temp_dir_parent=None,
    layer_timeout_seconds=3600,
    skip_timeout_layers=False,
    fallback_source_srs=None,
):
    """
    Convert CityGML to a multi-layer GeoPackage using ogr2ogr.

    A CityGML dataset may be a single .gml file or a ZIP holding many of them.
    The Dutch BGT/IMGeo export is the latter: one CityGML document per feature
    class (35 for a city extract — buildings, roads, water, vegetation, ...).
    Every member becomes its own GeoPackage layer, named after its filename, so
    the layer structure of the source survives into the tiles.

    Members that declare no srsName borrow the CRS declared by their siblings;
    without that, ogr2ogr cannot reproject them and silently drops every
    feature (bgt_pand.gml, the building layer, is one such member).

    The GeoPackage is assembled in a scratch directory and moved into place
    only once complete. SQLite's incremental writes are unreliable on
    bind-mounted volumes, where they surface as "disk I/O error" mid-run.

    Args:
        source_path: Path to .gml file or .zip containing CityGML
        output_path: Path to output .gpkg file
        progress_callback: Optional callback(stage, message) for progress updates
        temp_dir_parent: Parent directory for the scratch GeoPackage. Should
                        have room for the full output.

    Raises:
        RuntimeError: If no member converts successfully.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)

    if source_path.suffix.lower() == ".zip":
        sources = gml_sources_from_zip(source_path)
        archive = source_path
    else:
        # Single-file source: try to infer CRS from the file itself.
        sources = [(
            str(source_path),
            layer_name_for_gml(source_path.name),
            _extract_srs_from_file(source_path),
        )]
        archive = None

    total = len(sources)
    print(f"  Converting {total} CityGML layer(s) to GeoPackage...")
    _emit(progress_callback, "convert", f"Converting {total} CityGML layer(s)...")

    scratch_dir = tempfile.mkdtemp(prefix="citygml_", dir=str(temp_dir_parent) if temp_dir_parent else None)
    scratch_gpkg = Path(scratch_dir) / output_path.name
    converted, failed, tolerated, timed_out = [], [], [], []
    tolerated_details = {}
    failed_details = {}
    unresolved_crs_layers = []
    srs_diagnostics = []

    try:
        for index, (member, layer_name, source_srs) in enumerate(sources, start=1):
            unpacked = extract_member(archive, member, scratch_dir) if archive else None
            ogr_source = str(unpacked) if unpacked else member
            effective_source_srs = source_srs or fallback_source_srs
            srs_diagnostics.append({
                "layer": layer_name,
                "member": member,
                "detected_source_srs": source_srs or "",
                "fallback_source_srs": fallback_source_srs or "",
                "effective_source_srs": effective_source_srs or "",
                "force_srs_detection": True,
            })
            print(
                f"      SRS[{layer_name}]: detected={source_srs or '-'} "
                f"fallback={fallback_source_srs or '-'} effective={effective_source_srs or '-'}"
            )

            existed = scratch_gpkg.exists()
            plan = append_attempts(
                scratch_gpkg, ogr_source, layer_name,
                source_srs=effective_source_srs,
                source_open_options=["FORCE_SRS_DETECTION=YES"],
                gpkg_exists=existed,
            )

            strict_failure_summary = None
            strict_failure_tail = []
            try:
                for attempt, cmd in enumerate(plan):
                    if attempt and not existed:
                        scratch_gpkg.unlink(missing_ok=True)
                    cmd = [
                        cmd[0],
                        "--config", "GML_SRS_DIMENSION_IF_MISSING", "2",
                        *cmd[1:],
                    ]
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=max(1, int(layer_timeout_seconds or 3600)),
                        )
                    except subprocess.TimeoutExpired as exc:
                        if not skip_timeout_layers:
                            raise
                        timed_out.append(layer_name)
                        result = subprocess.CompletedProcess(
                            args=cmd,
                            returncode=124,
                            stdout=(exc.stdout or ""),
                            stderr=(exc.stderr or "") + f"\nTimed out after {int(layer_timeout_seconds or 3600)} seconds",
                        )
                        srs_diagnostics[-1]["last_attempt"] = int(attempt)
                        srs_diagnostics[-1]["last_exit_code"] = 124
                        break
                    if result.returncode == 0:
                        srs_diagnostics[-1]["last_attempt"] = int(attempt)
                        srs_diagnostics[-1]["last_exit_code"] = 0
                        break
                    srs_diagnostics[-1]["last_attempt"] = int(attempt)
                    srs_diagnostics[-1]["last_exit_code"] = int(result.returncode)
                    if attempt == 0:
                        strict_failure_summary = _summarize_stderr(result.stderr)
                        strict_failure_tail = (result.stderr or "").strip().splitlines()[-6:]
                        print(f"      {layer_name}: strict pass failed, retrying with -skipfailures")
            finally:
                if unpacked is not None:
                    unpacked.unlink(missing_ok=True)

            if result.returncode == 0:
                converted.append(layer_name)
                if attempt:
                    tolerated.append(layer_name)
                    retry_summary = _summarize_stderr(result.stderr)
                    tolerated_details[layer_name] = {
                        "strict_pass": strict_failure_summary,
                        "strict_tail": strict_failure_tail,
                        "retry_pass": retry_summary,
                    }
                    if _has_reason(strict_failure_summary, "crs_transform_error") and _has_reason(retry_summary, "crs_transform_error"):
                        unresolved_crs_layers.append(layer_name)
                srs_diagnostics[-1]["status"] = "ok" if not attempt else "ok_features_skipped"
                status = "ok" if not attempt else "ok (features skipped)"
            else:
                failed.append(layer_name)
                status = (
                    f"TIMEOUT ({int(layer_timeout_seconds or 3600)}s, skipped)"
                    if layer_name in timed_out
                    else f"FAILED (exit {result.returncode})"
                )
                failed_details[layer_name] = {
                    "attempt": int(attempt),
                    "summary": _summarize_stderr(result.stderr),
                }
                if _has_reason(failed_details[layer_name]["summary"], "crs_transform_error"):
                    unresolved_crs_layers.append(layer_name)
                srs_diagnostics[-1]["status"] = "failed"
                tail = (result.stderr or "").strip().splitlines()[-3:]
                for line in tail:
                    print(f"      {line}")

            print(f"    [{index}/{total}] {layer_name}: {status}")
            if layer_name in tolerated_details:
                strict_info = tolerated_details[layer_name].get("strict_pass") or {}
                reasons = strict_info.get("top_reasons") or []
                compact = ", ".join(f"{name}:{count}" for name, count in reasons[:3]) or "unknown"
                print(f"      skipped detail: strict pass issues={strict_info.get('issue_count', 0)}; causes: {compact}")
            _emit(progress_callback, "convert", f"Layer {index}/{total}: {layer_name} {status}")

        if not converted:
            raise CityGMLConversionError(
                f"ogr2ogr converted none of the {total} CityGML layer(s); "
                f"failed: {', '.join(failed)}",
                srs_diagnostics=srs_diagnostics,
                tolerated_details=tolerated_details,
                failed_details=failed_details,
                unresolved_crs_layers=unresolved_crs_layers,
            )

        if unresolved_crs_layers:
            unique_layers = sorted(set(unresolved_crs_layers))
            raise CityGMLConversionError(
                "CRS transform errors remain after FORCE_SRS_DETECTION and retry. "
                "Incoming layer CRS is unresolved or inconsistent. "
                f"Affected layers: {', '.join(unique_layers)}",
                srs_diagnostics=srs_diagnostics,
                tolerated_details=tolerated_details,
                failed_details=failed_details,
                unresolved_crs_layers=unique_layers,
            )

        # ogr2ogr exits 0 on a member that carries no features, so a member can
        # be "converted" and produce no layer at all. Ask the finished file what
        # actually arrived rather than trusting the exit codes.
        counts = layer_feature_counts(scratch_gpkg)
        empty = [name for name in converted if counts.get(name, 0) == 0]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(scratch_gpkg), str(output_path))

        size_mb = output_path.stat().st_size / (1024 * 1024)
        summary = f"{len(converted) - len(empty)}/{total} layers, {size_mb:.1f} MB"
        if failed:
            summary += f" ({len(failed)} failed: {', '.join(failed)})"
        if empty:
            # Named, not counted: a member truncated by a failed download and a
            # member that is legitimately empty are the same 0 here, and only
            # the name lets anyone tell them apart later.
            summary += f" ({len(empty)} empty: {', '.join(empty)})"
        if tolerated:
            # Named, not counted: these are the only layers whose feature count
            # may be short of the source, so anything quoted from them is caveated.
            summary += f" ({len(tolerated)} needed -skipfailures: {', '.join(tolerated)})"
        if timed_out:
            summary += f" ({len(timed_out)} timed out: {', '.join(timed_out)})"
        print(f"  Converted to GeoPackage: {output_path.name} — {summary}")
        _emit(progress_callback, "convert", f"CityGML converted: {summary}")

        return {
            "converted": converted,
            "failed": failed,
            "tolerated": tolerated,
            "empty": empty,
            "timed_out": timed_out,
            "tolerated_details": tolerated_details,
            "failed_details": failed_details,
            "srs_diagnostics": srs_diagnostics,
        }

    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _emit(progress_callback, stage, message):
    if progress_callback is not None:
        progress_callback(stage, message)


def extract_citygml_info(gml_path):
    """
    Extract basic info about CityGML file using ogrinfo.
    
    Returns dict with layer count and feature types.
    """
    try:
        result = subprocess.run(
            ["ogrinfo", str(gml_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Simple parsing - count layers and geometry types
        layer_count = result.stdout.count("Layer name:")
        has_buildings = "building" in result.stdout.lower()
        
        return {
            "layer_count": layer_count,
            "has_buildings": has_buildings,
            "info": result.stdout[:500],  # First 500 chars
        }
    except Exception as e:
        return {"error": str(e)}
