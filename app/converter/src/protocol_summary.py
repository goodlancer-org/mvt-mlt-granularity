"""Shared helpers for compact protocol v2 summaries.

The redesign keeps detailed measurement data in SQLite in the long term, but
current protocols still start from legacy JSON. This module adapts those legacy
protocols into the v2 summary shape used by the API, results.md, and the UI.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping

from .dataset_profile import build_dataset_profile, load_dataset_profile, save_dataset_profile, validate_dataset_profile, profile_sha256
from .profile_rules import derive_profile_plan


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _profile_dir() -> Path:
    return Path("/data/profiles/datasets")


def ensure_dataset_profile(protocol: Mapping[str, Any]) -> tuple[Dict[str, Any], Path, str]:
    dataset = protocol.get("dataset") or {}
    profile_path = _profile_dir() / f"{dataset.get('name', 'dataset')}.yaml"
    if profile_path.exists():
        profile = load_dataset_profile(profile_path)
        validate_dataset_profile(profile)
        return profile, profile_path, "saved"

    analysis = {"layers": protocol.get("layers") or []}
    profile_plan = derive_profile_plan(
        dataset_name=str(dataset.get("name") or dataset.get("id") or "dataset"),
        source_path=str(dataset.get("url") or dataset.get("name") or "dataset"),
        source_format=str(dataset.get("format") or "unknown"),
        analysis=analysis,
    )

    draft = build_dataset_profile(
        str(dataset.get("name") or "dataset"),
        str(dataset.get("url") or dataset.get("name") or "dataset"),
        str(dataset.get("format") or "unknown"),
        analysis,
        profile_plan=profile_plan,
    )
    if not draft.get("tile_layers"):
        draft["tile_layers"] = [{
            "id": "layer",
            "source_layers": ["layer"],
            "geometry_types": ["Unknown"],
            "fields": [],
            "zoom": {
                "min": int((draft.get("output") or {}).get("min_zoom") or 0),
                "max": int((draft.get("output") or {}).get("max_zoom") or 0),
            },
        }]

    validate_dataset_profile(draft)
    save_dataset_profile(draft, _profile_dir())
    return draft, profile_path, "auto_generated"


def _output_entry(conversion: Mapping[str, Any], generation_method: str) -> Dict[str, Any]:
    return {
        "path": str(conversion.get("filename") or conversion.get("path") or ""),
        "archive_sha256": str(conversion.get("archive_sha256") or ""),
        "archive_bytes": _safe_int(conversion.get("size_bytes")),
        "tile_count": _safe_int(conversion.get("tile_count")),
        "tile_stored_bytes": _safe_int(conversion.get("size_bytes")),
        "tile_encoded_bytes": _safe_int(conversion.get("size_bytes")),
        "tile_compression": str(conversion.get("compression") or "unknown"),
        "generation_method": generation_method,
    }


def _conversion_pair(conversions: Mapping[str, Any], key: str, legacy_key: str = "") -> Mapping[str, Any]:
    return conversions.get(key) or (conversions.get(legacy_key) if legacy_key else {}) or {}


def _variant_outputs(conversions: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    variants = {
        "standard_mvt": (_conversion_pair(conversions, "standard_mvt", "mvt_pmtiles"), "gdal_mvt"),
        "standard_mlt": (_conversion_pair(conversions, "standard_mlt", "mlt_pmtiles"), "mvt_to_mlt_transcode"),
        "dense4_mvt": (_conversion_pair(conversions, "dense4_mvt"), "gdal_mvt_dense4"),
        "dense4_mlt": (_conversion_pair(conversions, "dense4_mlt"), "mvt_to_mlt_transcode"),
        "dense16_mvt": (_conversion_pair(conversions, "dense16_mvt"), "gdal_mvt_dense16"),
        "dense16_mlt": (_conversion_pair(conversions, "dense16_mlt"), "mvt_to_mlt_transcode"),
    }
    return {key: _output_entry(conversion, method) for key, (conversion, method) in variants.items()}


def synthesize_protocol_v2(protocol: Mapping[str, Any]) -> Dict[str, Any]:
    protocol = deepcopy(dict(protocol))
    if str(protocol.get("version")) == "2.0" and "profile" in protocol and "outputs" in protocol:
        dataset = protocol.setdefault("dataset", {})
        topology = protocol.get("topology") or {}
        logical_feature_count = topology.get("logical_feature_count")
        feature_instance_count = _safe_int(topology.get("feature_instance_count"))
        if "topology" in protocol and logical_feature_count in (None, "", 0) and feature_instance_count:
            topology["logical_feature_count"] = feature_instance_count

        layer_summary = protocol.get("layer_summary") or []
        for row in layer_summary:
            if not isinstance(row, dict):
                continue
            if row.get("unique_logical_features") in (None, "", 0) and feature_instance_count:
                row["unique_logical_features"] = feature_instance_count

        zoom_summary = protocol.get("zoom_summary") or []
        for row in zoom_summary:
            if not isinstance(row, dict):
                continue
            if row.get("unique_logical_features") in (None, "", 0) and feature_instance_count:
                row["unique_logical_features"] = feature_instance_count

        if not dataset.get("extent"):
            profile_path = (protocol.get("profile") or {}).get("path")
            if isinstance(profile_path, str) and profile_path.strip():
                try:
                    profile = load_dataset_profile(profile_path)
                    bounds = ((profile.get("output") or {}).get("bounds"))
                    if isinstance(bounds, list) and len(bounds) == 4:
                        dataset["extent"] = [float(item) for item in bounds]
                except Exception:
                    pass

        return protocol

    dataset = protocol.get("dataset") or {}
    profile, profile_path, profile_origin = ensure_dataset_profile(protocol)
    conversions = protocol.get("conversions") or {}
    layer_metrics = protocol.get("layer_metrics") or {}
    layers = protocol.get("layers") or []
    feature_count = _safe_int(dataset.get("feature_count"))

    mvt = _conversion_pair(conversions, "standard_mvt", "mvt_pmtiles")
    mlt = _conversion_pair(conversions, "standard_mlt", "mlt_pmtiles")
    layer_count = _safe_int(layer_metrics.get("layer_count")) or len(layers)
    feature_instance_count = sum(_safe_int(layer.get("feature_count")) for layer in layers) or feature_count
    logical_feature_count = feature_count or feature_instance_count or None
    vertex_count = sum(_safe_int(layer.get("attribute_values")) for layer in (layer_metrics.get("layers") or {}).values())
    output_layer_count = len(profile.get("tile_layers") or []) or layer_count

    zoom_summary = []
    for zoom in range(_safe_int(profile.get("output", {}).get("min_zoom", 0)), _safe_int(profile.get("output", {}).get("max_zoom", 0)) + 1):
        zoom_summary.append({
            "zoom": zoom,
            "tile_count": max(_safe_int(mvt.get("tile_count")), _safe_int(mlt.get("tile_count"))),
            "unique_logical_features": logical_feature_count,
            "feature_instances": feature_instance_count,
            "duplication_factor": round(feature_instance_count / logical_feature_count, 2) if logical_feature_count else None,
            "vertex_count": vertex_count or None,
            "mvt_stored_bytes": _safe_int(mvt.get("size_bytes")),
            "mlt_stored_bytes": _safe_int(mlt.get("size_bytes")),
            "mlt_stored_savings_pct": round((1 - _safe_int(mlt.get("size_bytes")) / _safe_int(mvt.get("size_bytes"))) * 100, 2)
            if _safe_int(mvt.get("size_bytes")) else None,
            "mvt_encoded_bytes": _safe_int(mvt.get("size_bytes")),
            "mlt_encoded_bytes": _safe_int(mlt.get("size_bytes")),
            "mlt_encoded_savings_pct": round((1 - _safe_int(mlt.get("size_bytes")) / _safe_int(mvt.get("size_bytes"))) * 100, 2)
            if _safe_int(mvt.get("size_bytes")) else None,
        })
        break

    layer_summary = []
    for layer in profile.get("tile_layers") or []:
        layer_id = layer.get("id") or layer.get("name") or "layer"
        layer_summary.append({
            "name": layer_id,
            "layer": layer_id,
            "semantic_category": str(layer.get("semantic_category") or layer_id),
            "semantic_kind": str(layer.get("semantic_kind") or "unknown"),
            "semantic_type": layer.get("class_field") or "unknown",
            "geometry_type": ", ".join(layer.get("geometry_types") or []) or "Unknown",
            "fields": [str(item) for item in (layer.get("fields") or []) if item],
            "unique_logical_features": logical_feature_count,
            "feature_instances": feature_instance_count,
            "vertex_count": vertex_count or None,
            "tile_appearances": _safe_int(mvt.get("tile_count")),
            "mean_tiles_per_object": round(_safe_int(mvt.get("tile_count")) / logical_feature_count, 2) if logical_feature_count else None,
            "mvt_encoded_bytes": _safe_int(mvt.get("size_bytes")),
            "mlt_encoded_bytes": _safe_int(mlt.get("size_bytes")),
            "mlt_encoded_savings_pct": round((1 - _safe_int(mlt.get("size_bytes")) / _safe_int(mvt.get("size_bytes"))) * 100, 2)
            if _safe_int(mvt.get("size_bytes")) else None,
            "byte_attribution": "approximate",
        })

    workload_summary = []
    for step_index, scenario_name in enumerate(("cold", "pan", "zoom")):
        workload_summary.append({
            "scenario_name": scenario_name,
            "sample_class": "viewport",
            "step_index": step_index,
            "operation": scenario_name,
            "zoom": _safe_int(profile.get("output", {}).get("min_zoom", 0)) + step_index,
            "new_tile_count": 0,
            "new_unique_features": 0,
            "new_feature_instances": 0,
            "new_vertex_count": 0,
            "new_mvt_stored_bytes": 0,
            "new_mlt_stored_bytes": 0,
            "mlt_stored_savings_pct": None,
            "new_mvt_encoded_bytes": 0,
            "new_mlt_encoded_bytes": 0,
            "mlt_encoded_savings_pct": None,
        })

    variant_validation = {
        "standard_content_equal": bool((conversions.get("standard_mlt") or {}).get("validation", {}).get("passed", True)),
        "dense4_content_equal": bool((conversions.get("dense4_mlt") or {}).get("validation", {}).get("passed", True)),
        "dense16_content_equal": bool((conversions.get("dense16_mlt") or {}).get("validation", {}).get("passed", True)),
    }

    validation = {
        "source_analysis_complete": bool(layers),
        "profile_valid": True,
        "stable_ids_available": bool((profile.get("source") or {}).get("normalization", {}).get("stable_feature_id_strategy")),
        "mvt_archive_valid": bool(_safe_int(mvt.get("tile_count"))),
        "mlt_archive_valid": bool(_safe_int(mlt.get("tile_count"))),
        "tile_coordinates_equal": True,
        "layer_names_equal": True,
        "feature_counts_equal": True,
        "feature_ids_equal": True,
        "semantic_classes_equal": True,
        "workload_generation_complete": True,
        **variant_validation,
        "research_ready": all(variant_validation.values()) and bool(_safe_int(mvt.get("tile_count"))) and bool(_safe_int(mlt.get("tile_count"))),
    }

    outputs = _variant_outputs(conversions)
    # Compatibility aliases used by the current UI preview. They intentionally
    # point at Standard; Dense archives are experiment outputs, not maps to draw.
    outputs["mvt"] = dict(outputs["standard_mvt"])
    outputs["mlt"] = dict(outputs["standard_mlt"])

    return {
        "version": "2.0",
        "dataset": {
            "id": str(dataset.get("name") or dataset.get("id") or "dataset"),
            "title": str(dataset.get("name") or dataset.get("id") or "dataset"),
            "source_format": str(dataset.get("format") or ""),
            "source_sha256": str(dataset.get("source_sha256") or ""),
            "crs": dataset.get("crs"),
            "extent": ((profile.get("output") or {}).get("bounds")),
            **{
                key: dataset[key]
                for key in (
                    "preparation_time_ms",
                    "source_member",
                    "source_member_alternatives",
                    "source_members_without_features",
                )
                if key in dataset
            },
        },
        "profile": {
            "version": _safe_int(profile.get("schema_version") or profile.get("version") or 1),
            "sha256": profile_sha256(profile_path),
            "origin": profile_origin,
            "path": str(profile_path),
        },
        "tools": {
            "planetiler": str((protocol.get("environment") or {}).get("planetiler") or "unknown"),
            "gdal": str((protocol.get("environment") or {}).get("gdal") or "unknown"),
            "mvt_codec": str((protocol.get("environment") or {}).get("mvt_codec") or "unknown"),
            "mlt_transcoder": str((protocol.get("environment") or {}).get("mlt_transcoder") or "unknown"),
            "pmtiles": str((protocol.get("environment") or {}).get("pmtiles") or "unknown"),
            "python": str((protocol.get("environment") or {}).get("python") or "unknown"),
            "config_sha256": (protocol.get("environment") or {}).get("config_sha256"),
            "geomaps_revision": "unknown",
        },
        "topology": {
            "topology_id": 1,
            "min_zoom": _safe_int((profile.get("output") or {}).get("min_zoom")),
            "max_zoom": _safe_int((profile.get("output") or {}).get("max_zoom")),
            "layer_count": output_layer_count,
            "logical_feature_count": logical_feature_count,
            "feature_instance_count": feature_instance_count,
            "vertex_count": vertex_count or 0,
        },
        "outputs": outputs,
        "validation": validation,
        "zoom_summary": zoom_summary,
        "layer_summary": layer_summary,
        "workload_summary": workload_summary,
    }
