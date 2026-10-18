"""Generate and manage protocol JSON files."""

import json
import os
import hashlib
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .protocol_summary import synthesize_protocol_v2
from .protocol_v2 import write_protocol_v2


def _container_memory_bytes():
    """Total memory visible to this container, or None off Linux."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def capture_environment(cfg, *, cpu_count=None, total_memory_bytes=None):
    """Record the conditions a conversion ran under.

    conversion_time_ms and peak_memory_mb are reported results, so they only
    mean something next to the machine and settings that produced them. Heap
    size and available memory have already changed once mid-project, which is
    exactly the kind of difference that is invisible later without this.
    """
    packages = {}
    for package in ('mapbox-vector-tile', 'maplibre-tiles', 'pmtiles'):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = 'unknown'
    try:
        gdal = subprocess.check_output(['ogrinfo', '--version'], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        gdal = 'unknown'
    return {
        "python": platform.python_version(),
        "gdal": gdal,
        "mvt_codec": packages['mapbox-vector-tile'],
        "mlt_transcoder": packages['maplibre-tiles'],
        "pmtiles": packages['pmtiles'],
        "config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "java_heap": cfg.get("java_heap"),
        "min_zoom": cfg.get("min_zoom"),
        "max_zoom": cfg.get("max_zoom"),
        "cpu_count": cpu_count if cpu_count is not None else os.cpu_count(),
        "total_memory_bytes": (
            total_memory_bytes if total_memory_bytes is not None
            else _container_memory_bytes()
        ),
    }


# Numeric conversion metrics reported as a median over repeated runs. Archive
# size, tile count and feature count belong here too: they should not move
# between runs, so a non-zero spread on them is a nondeterminism warning.
_AGGREGATED_METRICS = (
    "time_seconds", "time_ms", "peak_memory_mb", "conversion_time_ms",
    "size_bytes", "output_size_bytes", "tile_count", "feature_count",
)


def aggregate_conversion_runs(runs):
    """Combine repeated conversions of one format into a single entry.

    A single Planetiler run is not a measurement. Nominally identical runs of
    the same source at the same heap differed by 8-28% in wall time -- larger
    than the MLT-vs-MVT difference the study reports -- so the reported figure
    is a median with the observed spread, as render metrics already are.

    Only successful runs contribute to the medians; exit_code is the worst
    observed, so one failure among three is never averaged away.
    """
    if not runs:
        return {}

    good = [r for r in runs if r.get("exit_code") == 0] or list(runs)
    out = dict(good[-1])
    out["runs"] = len(runs)
    out["exit_code"] = max(r.get("exit_code") or 0 for r in runs)
    out["spread"] = {}

    for metric in _AGGREGATED_METRICS:
        values = [r[metric] for r in good
                  if isinstance(r.get(metric), (int, float))]
        if not values:
            continue
        out[metric] = statistics.median(values)
        out["spread"][metric] = {"min": min(values), "max": max(values)}

    return out


def _with_paper_metric_names(conversions):
    """Add the metric names the paper defines, keeping the recorded ones.

    Intro.md names the preparation metrics conversion_time_ms, peak_memory_mb,
    output_size_bytes and tile_count. Two of those were never written: the data
    went into time_seconds and size_bytes, in different units, so a reader could
    look a metric up in the paper and find nothing by that name in a protocol.

    The originals stay. Several readers in the UI and this module use them, and
    the protocols already on disk carry them; adding is cheap, renaming would
    invalidate every conversion already run.
    """
    out = {}
    for key, data in conversions.items():
        # Measured milliseconds where they exist; protocols written before the
        # run was timed in milliseconds still derive theirs from the seconds.
        millis = data.get("time_ms")
        seconds = data.get("time_seconds")
        if millis is None and seconds is not None:
            millis = round(seconds * 1000)
        out[key] = {
            **data,
            "conversion_time_ms": millis,
            "output_size_bytes": data.get("size_bytes"),
        }
    return out


def generate_protocol(
    dataset_info,
    source_analysis,
    conversions,
    output_dir,
    environment=None,
):
    """
    Generate a comprehensive protocol JSON file.

    Args:
        dataset_info: dict with name, url, format
        source_analysis: dict from analyzer.analyze_source()
        conversions: dict of {format_key: {size_bytes, time_seconds, tile_count, ...}}
        output_dir: directory where protocol file will be saved

    Returns:
        Path to the generated protocol file
    """
    conversions = _with_paper_metric_names(conversions)

    protocol = {
        "version": "1.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Conditions the numbers were produced under; without these, protocols
        # from different heap sizes or machines look interchangeable.
        "environment": environment or {},
        "dataset": {
            "name": dataset_info["name"],
            "url": dataset_info.get("url", ""),
            "format": dataset_info.get("format", ""),
            "size_bytes": source_analysis.get("size_bytes", 0),
            "driver": source_analysis.get("driver", ""),
            "description": source_analysis.get("description", ""),
        },
        "layers": _build_layers(source_analysis),
        "conversions": conversions,
        "layer_metrics": compute_layer_metrics(
            conversions,
            declared_layers=[l.get("name") for l in source_analysis.get("layers", [])],
        ),
        "compression_ratios": _compute_ratios(conversions),
        "status": _compute_status(conversions),
        "summary": _build_summary(conversions),
    }

    # What was converted and what was passed over on the way there. Each is
    # written only when there is something to say: a key present with an empty
    # value would assert that the pipeline checked and found nothing, which is
    # not the same as a source where the question does not arise.
    #
    # dataset.url names the archive, and for a multi-edition download that is not
    # enough to say which map the figures describe. The Saentis ZIP holds German
    # and French editions of one sheet with identical structure, so converting
    # the other one changes no count anywhere.
    for key in ("source_member", "source_member_alternatives",
                "source_members_without_features", "preparation_time_ms"):
        value = dataset_info.get(key)
        if value:
            protocol["dataset"][key] = value

    normalization = dataset_info.get("normalization")
    if normalization:
        protocol["dataset"]["normalization"] = normalization
        if normalization.get("normalization_time_ms") is not None:
            protocol["dataset"]["normalization_time_ms"] = normalization["normalization_time_ms"]

    # Carry through dataset-level total feature count (set for OSM PBF sources)
    dataset_meta = source_analysis.get("dataset", {})
    if dataset_meta.get("feature_count"):
        protocol["dataset"]["feature_count"] = dataset_meta["feature_count"]

    # Add extent and CRS - prefer combined dataset extent (already in WGS84)
    if dataset_meta.get("extent"):
        protocol["dataset"]["extent"] = dataset_meta["extent"]
        protocol["dataset"]["crs"] = dataset_meta.get("crs", "EPSG:4326")
    else:
        # Fallback to first layer extent (may not be WGS84)
        layers = source_analysis.get("layers", [])
        if layers and layers[0].get("extent"):
            protocol["dataset"]["extent"] = layers[0]["extent"]
        if layers and layers[0].get("crs"):
            protocol["dataset"]["crs"] = layers[0]["crs"]

    # Write protocol file
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_path = output_dir / f"{dataset_info['name']}.json"

    protocol_v2 = synthesize_protocol_v2(protocol)
    write_protocol_v2(protocol_v2, protocol_path)
    print(f"\n  Protocol saved: {protocol_path}")
    return protocol_path


def _encoding_layers(conversions, encoding):
    """Layer stats for an encoding from the PMTiles research archive."""
    conversion = (
        conversions.get(f"standard_{encoding}")
        or conversions.get(f"{encoding}_pmtiles")
        or conversions.get(f"{encoding}_mbtiles")
        or {}
    )
    return conversion.get("layers") or {}


def compute_layer_metrics(conversions, declared_layers=None):
    """Per-layer size, share of the tile budget, and MLT-vs-MVT saving.

    Savings are negative where MLT encodes a layer into more bytes than MVT,
    which is common: MLT's columnar layout trades raw size for compressibility,
    so per-layer and archive-level savings do not have to agree.

    ``declared_layers`` is what the source analysis found, which is what the
    generated profile asks Planetiler for -- the profile's layer ids are those
    names verbatim. Any of them that produced no tiles is reported in
    ``layers_without_tiles`` rather than simply not appearing. Saentis declares
    28 layers and its tiles carry 27: ``Alluvial_and_Lacustrine_Structures_L``
    is absent and nothing anywhere said it had gone. It is most likely an empty
    source layer, but an empty layer and a layer whose conversion failed were
    indistinguishable in the output, and ``layer_count`` is one of the paper's
    eighteen metrics -- so a layer that vanishes quietly is a wrong figure, not
    untidiness.
    """
    mvt = _encoding_layers(conversions, "mvt")
    mlt = _encoding_layers(conversions, "mlt")

    names = sorted(set(mvt) | set(mlt))
    mvt_total = sum(l.get("size_bytes", 0) for l in mvt.values())
    mlt_total = sum(l.get("size_bytes", 0) for l in mlt.values())

    layers = {}
    for name in names:
        mvt_bytes = mvt.get(name, {}).get("size_bytes")
        mlt_bytes = mlt.get(name, {}).get("size_bytes")

        savings = None
        if mvt_bytes and mlt_bytes:
            savings = round((1 - mlt_bytes / mvt_bytes) * 100, 2)

        stats = mvt.get(name) or mlt.get(name) or {}
        feature_count = stats.get("feature_count", 0)
        attribute_values = stats.get("attribute_values", 0)

        layers[name] = {
            "size_bytes": {"mvt": mvt_bytes, "mlt": mlt_bytes},
            "size_share": {
                "mvt": round(mvt_bytes / mvt_total * 100, 2) if mvt_bytes and mvt_total else None,
                "mlt": round(mlt_bytes / mlt_total * 100, 2) if mlt_bytes and mlt_total else None,
            },
            "mlt_savings_pct": savings,
            "tile_count": stats.get("tile_count", 0),
            "feature_count": feature_count,
            # Attribute volume, not distinct-value cardinality: Planetiler
            # reports how many keys and values a layer encodes, which is what
            # MLT's dictionary encoding acts on.
            "attribute_keys": stats.get("attribute_keys", 0),
            "attribute_values": attribute_values,
            "attributes_per_feature": (
                round(attribute_values / feature_count, 2) if feature_count else None
            ),
        }

    missing = [n for n in (declared_layers or []) if n not in layers]

    return {
        "layer_count": len(layers),
        "layers": layers,
        "layers_without_tiles": missing,
    }


def _build_layers(source_analysis):
    """Build layers section from source analysis."""
    layers = []
    for layer in source_analysis.get("layers", []):
        layers.append({
            "name": layer.get("name", ""),
            "feature_count": layer.get("feature_count", 0),
            "geometry_type": layer.get("geometry_type", "Unknown"),
            "crs": layer.get("crs", ""),
            "extent": layer.get("extent", []),
            "fields": layer.get("fields", []),
        })
    return layers


def _compute_ratios(conversions):
    """Compute compression ratios between format combinations."""
    ratios = {}

    def safe_ratio(key_a, key_b, label):
        size_a = conversions.get(key_a, {}).get("size_bytes", 0)
        size_b = conversions.get(key_b, {}).get("size_bytes", 0)
        if size_b > 0 and size_a > 0:
            ratios[label] = round(size_a / size_b, 4)

    # MLT vs MVT for the standard tiling variant.
    safe_ratio("standard_mlt", "standard_mvt", "standard_mlt_vs_mvt")
    safe_ratio("mlt_pmtiles", "mvt_pmtiles", "mlt_vs_mvt_pmtiles")
    safe_ratio("dense4_mlt", "dense4_mvt", "dense4_mlt_vs_mvt")
    safe_ratio("dense16_mlt", "dense16_mvt", "dense16_mlt_vs_mvt")

    # Best vs worst
    sizes = {k: v.get("size_bytes", 0) for k, v in conversions.items() if v.get("size_bytes", 0) > 0}
    if sizes:
        best = min(sizes, key=sizes.get)
        worst = max(sizes, key=sizes.get)
        ratios["best_format"] = best
        ratios["worst_format"] = worst
        if sizes[worst] > 0:
            ratios["best_vs_worst"] = round(sizes[best] / sizes[worst], 4)

    return ratios


def _build_summary(conversions):
    """Build a human-readable summary."""
    lines = []
    for key, data in sorted(conversions.items()):
        size = data.get("size_bytes", 0)
        time_s = data.get("time_seconds", 0)
        tiles = data.get("tile_count", 0)
        mem_mb = data.get("peak_memory_mb")
        if size > 0:
            size_mb = size / (1024 * 1024)
            mem_str = f", {mem_mb:.0f} MB RAM" if mem_mb else ""
            lines.append(f"{key}: {size_mb:.2f} MB, {tiles} tiles, {time_s:.1f}s{mem_str}")
        else:
            lines.append(f"{key}: failed or empty")
    return "\n".join(lines)


def _compute_status(conversions):
    """Compute an overall dataset status from conversion results."""
    if not conversions:
        return "failed"
    if all(data.get("exit_code") == 0 for data in conversions.values()):
        return "completed"
    if any(data.get("exit_code") == 0 for data in conversions.values()):
        return "partial"
    return "failed"


def load_protocol(protocol_path):
    """Load a protocol JSON file."""
    return json.loads(Path(protocol_path).read_text(encoding="utf-8"))


def list_protocols(protocols_dir):
    """List all protocol files in a directory."""
    protocols_dir = Path(protocols_dir)
    if not protocols_dir.exists():
        return []
    return sorted(protocols_dir.glob("*.json"))
