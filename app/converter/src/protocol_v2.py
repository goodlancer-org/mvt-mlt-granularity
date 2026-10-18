"""Compact protocol v2 export for the redesign.

This module is intentionally small and schema-driven: the detailed data remains
in SQLite, while the protocol JSON is a compact reproducible summary for UI and
research exports. It mirrors the design contract in docs/geomaps_research_pipeline_redesign.md.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_protocol_v2(
    *,
    dataset: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_path: str,
    tools: Mapping[str, Any],
    topology: Mapping[str, Any],
    outputs: Mapping[str, Mapping[str, Any]],
    validation: Mapping[str, Any],
    zoom_summary: Sequence[Mapping[str, Any]],
    layer_summary: Sequence[Mapping[str, Any]],
    workload_summary: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build a schema-version-2 protocol export using the redesign contract."""
    profile_payload = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    profile_entry = {
        "version": int(profile.get("version") or 1),
        "sha256": _sha256_hex(profile_payload),
        "origin": "saved" if profile.get("dataset", {}).get("id") else "auto_generated",
        "path": str(profile_path),
    }

    protocol = {
        "version": "2.0",
        "dataset": {
            "id": str(dataset.get("id") or ""),
            "title": str(dataset.get("title") or ""),
            "source_format": str(dataset.get("source_format") or ""),
            "source_sha256": str(dataset.get("source_sha256") or ""),
            "crs": dataset.get("crs"),
        },
        "profile": profile_entry,
        "tools": {
            "planetiler": str(tools.get("planetiler") or "unknown"),
            "gdal": str(tools.get("gdal") or "unknown"),
            "mlt_transcoder": str(tools.get("mlt_transcoder") or "unknown"),
            "pmtiles": str(tools.get("pmtiles") or "unknown"),
            "geomaps_revision": str(tools.get("geomaps_revision") or "unknown"),
        },
        "topology": {
            "topology_id": int(topology.get("topology_id") or 0),
            "min_zoom": int(topology.get("min_zoom") or 0),
            "max_zoom": int(topology.get("max_zoom") or 0),
            "layer_count": int(topology.get("layer_count") or 0),
            "logical_feature_count": topology.get("logical_feature_count"),
            "feature_instance_count": int(topology.get("feature_instance_count") or 0),
            "vertex_count": int(topology.get("vertex_count") or 0),
        },
        "outputs": {},
        "validation": {str(k): bool(v) for k, v in (validation or {}).items()},
        "zoom_summary": [dict(item) for item in (zoom_summary or [])],
        "layer_summary": [dict(item) for item in (layer_summary or [])],
        "workload_summary": [dict(item) for item in (workload_summary or [])],
    }

    for encoding_name in ("mvt", "mlt"):
        entry = outputs.get(encoding_name) or {}
        protocol["outputs"][encoding_name] = {
            "path": str(entry.get("path") or ""),
            "archive_sha256": str(entry.get("archive_sha256") or ""),
            "archive_bytes": int(entry.get("archive_bytes") or 0),
            "tile_count": int(entry.get("tile_count") or 0),
            "tile_stored_bytes": int(entry.get("tile_stored_bytes") or 0),
            "tile_encoded_bytes": int(entry.get("tile_encoded_bytes") or 0),
            "tile_compression": str(entry.get("tile_compression") or "unknown"),
            "generation_method": str(entry.get("generation_method") or "unknown"),
        }

    return protocol


def write_protocol_v2(protocol: Mapping[str, Any], output_path: str | Path) -> Path:
    """Write a v2 protocol JSON file to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
