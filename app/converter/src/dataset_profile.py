"""Dataset-specific GEOMAPS conversion profiles.

These profiles are intentionally not just Planetiler YAML. The redesign treats
profile state as part of the research definition: it records how a dataset is
normalized, which layers become semantic tile layers, which fields are kept, and
which stable feature ID strategy is chosen.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml


def sanitize_dataset_id(name: str) -> str:
    """Return a filesystem-safe dataset identifier used for profile files."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "dataset").strip("._-")
    return slug.lower() or "dataset"


def dataset_profiles_dir(base_dir: str | Path | None = None) -> Path:
    """Return the directory used for persisted dataset profiles."""
    base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[1] / "profiles"
    if base.name == "datasets":
        return base
    return base / "datasets"


def _profile_template(dataset_name: str, source_path: str, source_format: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset": {
            "id": dataset_name,
            "source_path": source_path,
            "source_format": source_format,
            "name": dataset_name,
        },
        "source": {
            "selection": {
                "strategy": "auto",
                "primary_file": source_path,
            },
            "normalization": {
                "stable_feature_id_strategy": "source_primary_key",
                "feature_id_field": None,
                "semantic_categories": [],
            },
        },
        "tile_layers": [],
        "output": {
            "tile_format": "mvt",
            "container": "pmtiles",
            "min_zoom": 0,
            "max_zoom": 14,
            "encoding_pair": ["mvt", "mlt"],
        },
    }


def build_dataset_profile(
    dataset_name: str,
    source_path: str | Path,
    source_format: str,
    analysis: Optional[Dict[str, Any]] = None,
    profile_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a deterministic draft profile for a dataset."""
    profile = _profile_template(dataset_name, str(source_path), source_format)
    layers = analysis.get("layers", []) if analysis else []

    semantic_layers: List[Dict[str, Any]] = []
    for layer in layers:
        name = layer.get("name") or "unnamed_layer"
        fields = [field.get("name") for field in layer.get("fields", []) if field.get("name")]
        semantic_layers.append({
            "id": name,
            "source_layers": [name],
            "class_field": fields[0] if fields else None,
            "fields": fields,
            "geometry_types": [layer.get("geometry_type", "Unknown")],
            "zoom": {"min": 0, "max": 14},
        })

    if profile_plan:
        normalization_plan = profile_plan.get("normalization") or {}
        if isinstance(normalization_plan, Mapping):
            if normalization_plan.get("stable_feature_id_strategy"):
                profile["source"]["normalization"]["stable_feature_id_strategy"] = str(
                    normalization_plan["stable_feature_id_strategy"]
                )
            if "feature_id_field" in normalization_plan:
                profile["source"]["normalization"]["feature_id_field"] = normalization_plan.get("feature_id_field")

        output_plan = profile_plan.get("output") or {}
        if "min_zoom" in output_plan:
            profile["output"]["min_zoom"] = int(output_plan["min_zoom"])
        if "max_zoom" in output_plan:
            profile["output"]["max_zoom"] = int(output_plan["max_zoom"])
        if "bounds" in output_plan:
            bounds = output_plan.get("bounds")
            if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
                profile["output"]["bounds"] = [float(item) for item in bounds]

        planned_layers = profile_plan.get("tile_layers") or []
        if planned_layers:
            semantic_layers = []
            for layer in planned_layers:
                if not isinstance(layer, Mapping):
                    continue
                layer_id = str(layer.get("id") or layer.get("name") or "layer").strip()
                source_layers = [str(item) for item in (layer.get("source_layers") or []) if item]
                if not layer_id or not source_layers:
                    continue
                semantic_layers.append({
                    "id": layer_id,
                    "semantic_category": str(layer.get("semantic_category") or layer_id),
                    "source_layers": source_layers,
                    "source_layer_prefixes": [str(item) for item in (layer.get("source_layer_prefixes") or []) if item],
                    "class_field": layer.get("class_field"),
                    "fields": [str(item) for item in (layer.get("fields") or []) if item],
                    "geometry_types": [str(item) for item in (layer.get("geometry_types") or []) if item],
                    "semantic_kind": str(layer.get("semantic_kind") or "unknown"),
                    "zoom": {
                        "min": int((layer.get("zoom") or {}).get("min", profile["output"]["min_zoom"])),
                        "max": int((layer.get("zoom") or {}).get("max", profile["output"]["max_zoom"])),
                    },
                })

        planned_categories = profile_plan.get("semantic_categories") or []
        if planned_categories:
            profile["source"]["normalization"]["semantic_categories"] = [
                {
                    "id": str(item.get("id") or "layer"),
                    "name": str(item.get("name") or item.get("id") or "layer"),
                }
                for item in planned_categories
                if isinstance(item, Mapping)
            ]

    profile["tile_layers"] = semantic_layers
    if not profile["source"]["normalization"].get("semantic_categories"):
        profile["source"]["normalization"]["semantic_categories"] = [
            {"id": layer["id"], "name": layer["id"]} for layer in semantic_layers
        ]
    return profile


def _yaml_dump(profile: Dict[str, Any]) -> str:
    return yaml.safe_dump(profile, sort_keys=False, default_flow_style=False)


def save_dataset_profile(profile: Dict[str, Any], profiles_dir: str | Path) -> Path:
    """Persist a dataset profile to the dataset-specific profiles directory."""
    directory = dataset_profiles_dir(profiles_dir)
    directory.mkdir(parents=True, exist_ok=True)
    dataset_name = sanitize_dataset_id(str(profile["dataset"]["id"]))
    path = directory / f"{dataset_name}.yaml"
    path.write_text(_yaml_dump(profile), encoding="utf-8")
    return path


def load_dataset_profile(profile_path: str | Path) -> Dict[str, Any]:
    """Load a YAML dataset profile."""
    path = Path(profile_path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def resolve_dataset_profile(
    dataset_name: str,
    profiles_dir: str | Path,
    *,
    create_if_missing: bool = False,
    source_path: str | Path | None = None,
    source_format: str = "auto",
    analysis: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Return persisted profile path for a dataset if it exists.

    If create_if_missing is enabled, a draft profile is generated and saved.
    """
    directory = dataset_profiles_dir(profiles_dir)
    if not directory.exists():
        if not create_if_missing:
            return None
        directory.mkdir(parents=True, exist_ok=True)

    candidate_name = sanitize_dataset_id(dataset_name)
    profile_path = directory / f"{candidate_name}.yaml"
    if profile_path.exists():
        return profile_path

    if create_if_missing:
        draft = build_dataset_profile(candidate_name, source_path or dataset_name, source_format, analysis)
        return save_dataset_profile(draft, directory)
    return None


def validate_dataset_profile(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate a dataset profile against the PMTiles-only research schema."""
    if not isinstance(profile, Mapping):
        raise ValueError("Dataset profile must be a mapping.")

    dataset = profile.get("dataset") or {}
    output = profile.get("output") or {}
    source = profile.get("source") or {}
    normalization = source.get("normalization") or {}
    tile_layers = profile.get("tile_layers") or []

    dataset_id = str(dataset.get("id") or "").strip()
    if not dataset_id:
        raise ValueError("Dataset profile requires a non-empty dataset.id.")

    container = str(output.get("container", "")).lower()
    if container != "pmtiles":
        raise ValueError("Dataset profile must use PMTiles as the research container.")

    if "mvt" not in [str(item).lower() for item in output.get("encoding_pair", [])]:
        raise ValueError("Dataset profile must include the canonical MVT encoding.")

    if "mlt" not in [str(item).lower() for item in output.get("encoding_pair", [])]:
        raise ValueError("Dataset profile must include the MLT transcode encoding.")

    strategy = str(normalization.get("stable_feature_id_strategy", "")).strip()
    if not strategy:
        raise ValueError("Dataset profile is missing stable_feature_id_strategy.")

    if not isinstance(tile_layers, list) or not tile_layers:
        raise ValueError("Dataset profile must define at least one output tile layer.")

    for layer in tile_layers:
        if not isinstance(layer, Mapping):
            raise ValueError("Each tile layer entry must be a mapping.")
        layer_id = str(layer.get("id") or layer.get("name") or "").strip()
        source_layers = layer.get("source_layers") or []
        if not layer_id:
            raise ValueError("Each tile layer entry requires an id.")
        if not isinstance(source_layers, list) or not source_layers:
            raise ValueError(f"Tile layer '{layer_id}' must define source_layers.")

    return profile


def validate_topology_equality(mvt_tiles: Mapping[str, Any], mlt_tiles: Mapping[str, Any]) -> bool:
    """Ensure the canonical MVT and MLT tile sets match on logical topology.

    The comparison is intentionally strict: tile coordinates, layer names, and
    feature IDs must be identical for the standard MVT/MLT research pair.
    """
    if not isinstance(mvt_tiles, Mapping) or not isinstance(mlt_tiles, Mapping):
        raise ValueError("Topology validation requires mappings of tile identifiers to layer payloads.")

    mvt_coords = set(mvt_tiles)
    mlt_coords = set(mlt_tiles)
    if mvt_coords != mlt_coords:
        raise ValueError(f"Topology mismatch: MVT and MLT tile coordinate sets differ ({sorted(mvt_coords)[:5]} vs {sorted(mlt_coords)[:5]}).")

    for coord in sorted(mvt_coords):
        mvt_layers = mvt_tiles.get(coord) or {}
        mlt_layers = mlt_tiles.get(coord) or {}
        if not isinstance(mvt_layers, Mapping) or not isinstance(mlt_layers, Mapping):
            raise ValueError(f"Topology mismatch at {coord}: non-mapping layer payload.")
        if set(mvt_layers) != set(mlt_layers):
            raise ValueError(f"Topology mismatch at {coord}: layer names differ between MVT and MLT.")

        for layer_name in sorted(mvt_layers):
            mvt_layer = mvt_layers.get(layer_name) or {}
            mlt_layer = mlt_layers.get(layer_name) or {}
            if not isinstance(mvt_layer, Mapping) or not isinstance(mlt_layer, Mapping):
                raise ValueError(f"Topology mismatch at {coord}/{layer_name}: layer payload is not mapping.")

            if mvt_layer.get("feature_count") != mlt_layer.get("feature_count"):
                raise ValueError(f"Topology mismatch at {coord}/{layer_name}: feature_count differs.")

            mvt_ids = mvt_layer.get("feature_ids") or []
            mlt_ids = mlt_layer.get("feature_ids") or []
            if list(mvt_ids) != list(mlt_ids):
                raise ValueError(f"Topology mismatch at {coord}/{layer_name}: feature_ids differ.")

            mvt_type_counts = mvt_layer.get("geometry_type_counts") or {}
            mlt_type_counts = mlt_layer.get("geometry_type_counts") or {}
            if dict(mvt_type_counts) != dict(mlt_type_counts):
                raise ValueError(f"Topology mismatch at {coord}/{layer_name}: geometry_type_counts differ.")

    return True


def profile_sha256(profile_path: str | Path) -> str:
    """Return the SHA-256 digest of the YAML content on disk."""
    data = Path(profile_path).read_bytes()
    return hashlib.sha256(data).hexdigest()
