"""Profile planning rules derived from offline map analysis facts.

The dataset profile is the reproducible contract for how source structure is
interpreted. This module loads optional YAML rules and derives a per-dataset
profile plan that can be applied in both protocol/profile generation and
Stage B tile generation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from .semantic_taxonomy import infer_semantic_kind


DEFAULT_RULES_PATH = "/profiles/profile_rules.yaml"


def _normalize_token(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9._-]+", "_", text).strip("._-")


def _clean_layer_id(value: str | None, fallback: str = "layer") -> str:
    token = _normalize_token(value)
    return token or fallback


def load_profile_rules(path: str | Path | None) -> Dict[str, Any]:
    """Load YAML profile rules, returning an empty mapping when absent."""
    candidate = Path(path or DEFAULT_RULES_PATH)
    if not candidate.exists():
        return {}
    data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _value_matches(match_values: Any, candidates: Iterable[str]) -> bool:
    if isinstance(match_values, str):
        values = [match_values]
    elif isinstance(match_values, list):
        values = match_values
    else:
        return False

    normalized_candidates = {_normalize_token(c) for c in candidates if c}
    for value in values:
        if _normalize_token(value) in normalized_candidates:
            return True
    return False


def _select_dataset_rule(
    rules: Mapping[str, Any],
    *,
    dataset_name: str,
    source_path: str,
    source_format: str,
) -> Mapping[str, Any] | None:
    entries = rules.get("datasets") or []
    if not isinstance(entries, list):
        return None

    candidates = [
        dataset_name,
        Path(source_path).name,
        Path(source_path).stem,
        source_format,
    ]

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        match = entry.get("match") or {}
        if not isinstance(match, Mapping):
            continue

        if _value_matches(match.get("dataset_ids"), candidates):
            return entry
        if _value_matches(match.get("source_names"), candidates):
            return entry

        contains = match.get("contains")
        if isinstance(contains, str):
            contains = [contains]
        if isinstance(contains, list):
            blob = " ".join(_normalize_token(c) for c in candidates)
            if any(_normalize_token(part) and _normalize_token(part) in blob for part in contains):
                return entry

    return None


def _detect_source_kind(source_format: str, dataset_rule: Mapping[str, Any] | None) -> str:
    if dataset_rule and dataset_rule.get("source_kind"):
        return str(dataset_rule.get("source_kind")).strip().lower()

    fmt = str(source_format or "").strip().lower()
    if fmt in {"tif", "tiff", "raster"}:
        raise ValueError("Raster sources are not part of the active GEOMAPS vector pipeline.")
    return "vector"


def _layer_fields(layer: Mapping[str, Any]) -> List[str]:
    values = []
    for field in layer.get("fields") or []:
        if isinstance(field, Mapping):
            name = field.get("name")
        else:
            name = field
        if name:
            values.append(str(name))
    return values


def _pick_class_field(fields: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    by_lower = {str(item).lower(): str(item) for item in fields if item}
    for candidate in candidates:
        found = by_lower.get(str(candidate).lower())
        if found:
            return found
    return None


def _glob_match(pattern: str, value: str) -> bool:
    expr = re.escape(str(pattern or "")).replace("\\*", ".*")
    return re.match(f"^{expr}$", str(value or "")) is not None


def _match_source_layers(
    source_layers: Iterable[str],
    *,
    all_layers: Iterable[str],
    source_layer_prefixes: Iterable[str],
) -> List[str]:
    selected: List[str] = []
    seen = set()

    for item in source_layers:
        name = str(item).strip()
        if not name:
            continue
        if name not in seen:
            selected.append(name)
            seen.add(name)

    all_items = [str(layer) for layer in all_layers if layer]
    prefixes = [str(prefix).strip() for prefix in source_layer_prefixes if str(prefix).strip()]
    for layer_name in sorted(all_items):
        if any(_glob_match(prefix, layer_name) for prefix in prefixes) and layer_name not in seen:
            selected.append(layer_name)
            seen.add(layer_name)
    return selected


def _normalize_tile_layers(
    tile_layers: Any,
    *,
    default_min_zoom: int,
    default_max_zoom: int,
    analysis_layers: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(tile_layers, list):
        return out

    available_layer_names = [str(layer.get("name") or "").strip() for layer in analysis_layers if isinstance(layer, Mapping)]

    for index, layer in enumerate(tile_layers, start=1):
        if not isinstance(layer, Mapping):
            continue
        layer_id = _clean_layer_id(layer.get("id") or layer.get("name"), fallback=f"layer_{index}")
        source_layers = [str(item) for item in (layer.get("source_layers") or []) if item]
        source_layer_prefixes = [str(item) for item in (layer.get("source_layer_prefixes") or []) if item]
        source_layers = _match_source_layers(
            source_layers,
            all_layers=available_layer_names,
            source_layer_prefixes=source_layer_prefixes,
        )
        if source_layer_prefixes and not source_layers:
            continue
        if not source_layers:
            source_layers = [layer_id]

        zoom = layer.get("zoom") or {}
        min_zoom = int(zoom.get("min", default_min_zoom))
        max_zoom = int(zoom.get("max", default_max_zoom))

        out.append(
            {
                "id": layer_id,
                "source_layers": source_layers,
                "source_layer_prefixes": source_layer_prefixes,
                "class_field": layer.get("class_field"),
                "fields": [str(item) for item in (layer.get("fields") or []) if item],
                "geometry_types": [str(item) for item in (layer.get("geometry_types") or []) if item],
                "zoom": {"min": min_zoom, "max": max_zoom},
                "semantic_category": layer.get("semantic_category") or layer_id,
                "semantic_kind": layer.get("semantic_kind")
                or infer_semantic_kind(layer.get("semantic_category") or layer_id, layer_id, " ".join(source_layers)),
            }
        )

    return out


def _auto_vector_layers(
    analysis_layers: Iterable[Mapping[str, Any]],
    *,
    default_min_zoom: int,
    default_max_zoom: int,
    class_field_candidates: List[str],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for layer in analysis_layers:
        name = str(layer.get("name") or "").strip()
        if not name:
            continue

        category = _clean_layer_id(layer.get("semantic_category") or name)
        state = grouped.setdefault(
            category,
            {
                "id": category,
                "source_layers": [],
                "fields": [],
                "geometry_types": set(),
                "zoom": {"min": default_min_zoom, "max": default_max_zoom},
                "semantic_category": category,
            },
        )
        state["source_layers"].append(name)

        geometry = str(layer.get("geometry_type") or "Unknown")
        state["geometry_types"].add(geometry)

        for field_name in _layer_fields(layer):
            if field_name not in state["fields"]:
                state["fields"].append(field_name)

    output: List[Dict[str, Any]] = []
    for category in sorted(grouped):
        item = grouped[category]
        item_fields = item.get("fields") or []
        class_field = _pick_class_field(item_fields, class_field_candidates)
        output.append(
            {
                "id": item["id"],
                "source_layers": sorted(dict.fromkeys(item["source_layers"])),
                "class_field": class_field,
                "fields": item_fields,
                "geometry_types": sorted(item["geometry_types"]),
                "zoom": item["zoom"],
                "semantic_category": item.get("semantic_category") or item["id"],
                "semantic_kind": infer_semantic_kind(item.get("semantic_category") or item["id"], item["id"]),
            }
        )

    return output


def derive_profile_plan(
    *,
    dataset_name: str,
    source_path: str,
    source_format: str,
    analysis: Optional[Mapping[str, Any]],
    rules_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Build a dataset profile plan from YAML rules plus source analysis."""
    rules = load_profile_rules(rules_path)
    defaults = rules.get("defaults") or {}

    default_min_zoom = int(defaults.get("min_zoom", 0))
    default_max_zoom = int(defaults.get("max_zoom", 14))
    class_field_candidates = [
        str(item)
        for item in (defaults.get("class_field_candidates") or ["class", "type", "category", "subclass", "kind", "featurecla"])
        if item
    ]

    dataset_rule = _select_dataset_rule(
        rules,
        dataset_name=dataset_name,
        source_path=source_path,
        source_format=source_format,
    )

    source_kind = _detect_source_kind(source_format, dataset_rule)

    output_cfg = dict((dataset_rule or {}).get("output") or {})
    min_zoom = int(output_cfg.get("min_zoom", default_min_zoom))
    max_zoom = int(output_cfg.get("max_zoom", default_max_zoom))
    bounds = output_cfg.get("bounds")

    if isinstance(bounds, str):
        bounds = [part.strip() for part in bounds.split(",") if part.strip()]
    if isinstance(bounds, tuple):
        bounds = list(bounds)
    if not (isinstance(bounds, list) and len(bounds) == 4):
        bounds = None
    else:
        try:
            bounds = [float(part) for part in bounds]
        except (TypeError, ValueError):
            bounds = None

    analysis_layers = (analysis or {}).get("layers") or []

    plan_tile_layers = _normalize_tile_layers(
        (dataset_rule or {}).get("tile_layers"),
        default_min_zoom=min_zoom,
        default_max_zoom=max_zoom,
        analysis_layers=analysis_layers,
    )

    if not plan_tile_layers and source_kind == "vector":
        plan_tile_layers = _auto_vector_layers(
            analysis_layers,
            default_min_zoom=min_zoom,
            default_max_zoom=max_zoom,
            class_field_candidates=class_field_candidates,
        )

    semantic_categories = [
        {
            "id": _clean_layer_id(layer.get("semantic_category") or layer.get("id"), fallback="layer"),
            "name": _clean_layer_id(layer.get("semantic_category") or layer.get("id"), fallback="layer"),
            "kind": str(layer.get("semantic_kind") or infer_semantic_kind(layer.get("semantic_category") or layer.get("id"))),
        }
        for layer in plan_tile_layers
    ]

    return {
        "source_kind": source_kind,
        "output": {"min_zoom": min_zoom, "max_zoom": max_zoom, "bounds": bounds},
        "tile_layers": plan_tile_layers,
        "semantic_categories": semantic_categories,
        "normalization": dict((dataset_rule or {}).get("normalization") or {}),
        "rule_name": (dataset_rule or {}).get("name"),
    }
