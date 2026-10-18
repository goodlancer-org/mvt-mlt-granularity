"""Configuration loader for the converter."""

import os
from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "data_dir": "/data",
    "normalized_dir": "/data/normalized",
    "normalization_crs": "EPSG:3857",
    "profiles_dir": "/profiles",
    "profile_rules_path": "/profiles/profile_rules.yaml",
    "min_zoom": 0,
    "max_zoom": 14,
    "tmp_dir": "/scratch",  # GDAL scratch must live on the host-mounted temp dir
    # CityGML preprocessing can be heavy (BGT/IMGeo). Keep the timeout explicit
    # and optionally allow continuing after timed-out members.
    "citygml_layer_timeout_seconds": 3600,
    "citygml_skip_timeout_layers": False,
    # Optional fallback for CityGML members where CRS cannot be inferred.
    # Example for PDOK/BGT: EPSG:28992
    "citygml_fallback_source_srs": "",
    # Emit extra diagnostics about layer-matching and feature filtering.
    # Enabled by default for the UI workflow so conversion logs always show
    # source-layer matching, include_when decisions and skip traces.
    "debug_filtering": True,
    # For repeated local runs, avoid persisting downloaded sources and layerstats
    # on the bind-mounted /data volume. The measured outputs are the final PMTiles
    # archives; keeping the large intermediate artifacts makes disk usage grow
    # fast across many conversions.
    "keep_sources": False,
    "keep_layerstats": False,
    # The active study compares canonical MVT and MLT on the same logical tile
    # topology. Browser timing and MBTiles compatibility remain optional,
    # diagnostics, not standard result generation.
    "conversion_repeats": 1,
    "overzoom_levels": [0],
    "gdal_dense_variants": [
        {"key": "standard", "detail_offset": 0, "extent": 4096},
        {"key": "dense4", "detail_offset": 1, "extent": 8192},
        {"key": "dense16", "detail_offset": 2, "extent": 16384},
    ],
    # Dense variants scale extent with geographic tile size, so one shared
    # simplification regime keeps native geographic LOD equivalent across
    # Standard/Dense-4/Dense-16.
    "gdal_simplification": 1.6,
    "gdal_simplification_max_zoom": 1.0,
    # Keep large limits so GDAL does not silently drop features/precision.
    "gdal_max_size": 2147483647,
    "gdal_max_features": 2147483647,
    # Validation mode for Stage B post-processing:
    # none | fast | full. Fast is the default for batch experiments.
    "gdal_validation_mode": "fast",
    # Tile limits mode:
    # experimental_unlimited keeps large limits for no-drop experiments,
    # safe applies conservative defaults unless explicit smaller limits are set.
    "gdal_tile_limits_mode": "experimental_unlimited",
    # Structural overzoom (src/structural_overzoom.py) is off unless configured.
    "formats": [
        {"tile_format": "mvt", "container": "pmtiles"},
        {"tile_format": "mlt", "container": "pmtiles"},
    ],
}


def validate_research_formats(formats):
    """Reject legacy MBTiles entries from standard research runs.

    The redesign makes PMTiles the only research container. MBTiles may remain
    behind compatibility switches for migration work, but it must never be part
    of the active result matrix or standard generation config.
    """
    for combo in formats or []:
        container = str(combo.get("container", "")).lower()
        if container == "mbtiles":
            raise ValueError(
                "MBTiles is not part of the standard GEOMAPS research pipeline; "
                "use PMTiles only."
            )
    return list(formats or [])


MOUNTED_TMP_DIR = Path("/scratch")


def resolve_tmp_dir(configured, mounted=MOUNTED_TMP_DIR):
    """The GDAL scratch directory to use in this environment.

    settings.yaml is shared between machines, and a tmp_dir that names one
    machine's disk (e.g. /mnt/secondPartition/scratch on the Linux
    host) does not exist on another (a Mac under Colima). GDAL would
    then create it inside the container's writable layer, on the VM disk.
    Where neither the path nor its parent exists but docker-compose's scratch
    mount does, use the mount. A path that exists is always kept.
    """
    if not configured:
        return mounted.as_posix()
    path = Path(configured)
    if not path.exists() and not path.parent.exists() and Path(mounted).exists():
        print(f"  tmp_dir {configured} does not exist here; using the mounted {mounted} instead")
        return mounted.as_posix()
    return str(configured)


def load_config(config_path=None):
    """Load config from YAML file, merged with defaults."""
    cfg = dict(DEFAULT_CONFIG)

    # Always apply repository-level baseline config when present.
    base_config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if base_config_path.exists():
        with open(base_config_path, "r", encoding="utf-8") as f:
            base_cfg = yaml.safe_load(f) or {}
        cfg.update(base_cfg)

    # Optional runtime override (API settings.yaml or --config path).
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        cfg.update(user_cfg)

    # Keep GDAL scratch on the host-mounted directory instead of the
    # container writable layer, also when settings name another machine's disk.
    cfg["tmp_dir"] = resolve_tmp_dir(cfg.get("tmp_dir"))

    # Allow env overrides
    if os.environ.get("CITYGML_LAYER_TIMEOUT_SECONDS"):
        cfg["citygml_layer_timeout_seconds"] = int(os.environ["CITYGML_LAYER_TIMEOUT_SECONDS"])
    if os.environ.get("CITYGML_SKIP_TIMEOUT_LAYERS"):
        cfg["citygml_skip_timeout_layers"] = (
            str(os.environ["CITYGML_SKIP_TIMEOUT_LAYERS"]).strip().lower() in {"1", "true", "yes", "on"}
        )
    if os.environ.get("CITYGML_FALLBACK_SOURCE_SRS"):
        cfg["citygml_fallback_source_srs"] = str(os.environ["CITYGML_FALLBACK_SOURCE_SRS"]).strip()
    if os.environ.get("DEBUG_FILTERING"):
        cfg["debug_filtering"] = (
            str(os.environ["DEBUG_FILTERING"]).strip().lower() in {"1", "true", "yes", "on"}
        )
    elif os.environ.get("DISABLE_DEBUG_FILTERING"):
        cfg["debug_filtering"] = not (
            str(os.environ["DISABLE_DEBUG_FILTERING"]).strip().lower() in {"1", "true", "yes", "on"}
        )

    validate_research_formats(cfg.get("formats", []))
    return cfg
