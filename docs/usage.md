# Convert, inspect and render maps

For the complete sequence, including exact corpus filenames, analysis and
dataset export, follow [From source maps to a Zenodo dataset](end-to-end.md).

## Requirements and paths

Use Python 3.12–3.14 and `uv` for analysis; Docker Compose supplies GDAL 3.13.3,
the PMTiles CLI and the converter's pinned Python packages. Node 22 is needed
only for frontend development. Windows users should run Linux containers in Docker.

All working paths are inside the repository. Docker sees `app/data` as `/data`
and `app/data/scratch` as `/scratch`. Put a large local import under
`app/data/sources/<id>/` and enter its `/data/sources/<id>/...` path in the UI.
Profiles are in `app/data/profiles/datasets`; classifier rules are in
`app/converter/profiles/profile_rules.yaml`. No source maps are committed.

Supported vector inputs include OSM PBF, GeoPackage, GeoJSON, Shapefile,
GeoParquet and GDAL-readable GML/CityGML or Interlis sources. Existing measurements
use normalized GeoPackages and paired MVT/MLT PMTiles archives. If those files
are already present at the registered paths, use the
[analysis-only workflow](end-to-end.md#already-have-normalized-maps-and-tile-archives)
and skip normalization and tile generation.

## Browser workflow

1. Run `python manage.py up` and open http://localhost:8080.
2. Choose upload, URL or an existing local source. Use a stable dataset name.
3. Inspect the proposed layers and choose bounds before normalization. The default
   canonical CRS is EPSG:3857; a profile can request geometry repair or clipping.
4. Normalize. Keep `<id>.gpkg` and `<id>.normalization.json` together: the manifest
   records source identity, CRS, selection, counts and hashes.
5. Review the dataset profile and zoom range, then generate tiles from the GPKG.
   Stage B creates Standard, Dense-4 and Dense-16 MVT/MLT pairs.
6. Open the map detail view, preview Standard tiles and edit layer style settings.
   Styling affects display; changing normalization or tiling settings requires
   regenerating the affected artifacts.

The converter serializes jobs so they do not compete for measured resources.
Cancellation and detailed progress are available in the UI. Inspect protocol
JSON and logs when a source fails; do not accept a silently empty layer plan.

## Command-line conversion

```sh
python manage.py convert --url /data/sources/example/example.gpkg --name example
```

`convert` runs inside the same converter container and accepts the converter's
arguments, including `--profile`, `--format` and `--config`. For bounds, layer
mapping and separate Stage A / Stage B control, use the web interface and saved
dataset profiles. Configuration is in `app/converter/config.yaml`; `max_zoom`
defaults to 14. Actual corpus profile zoom ranges and extents remain authoritative.

Use `gdal_validation_mode: full` for full pair checking; `fast` is the default.
Keep `gdal_tile_limits_mode: experimental_unlimited` to reproduce the no-drop
experiment. `safe` enforces practical tile limits and changes the experiment.

## Figures

```sh
python manage.py maps --dpi 450
python manage.py maps --input-dir app/data/output --output-dir outputs/map-panels
```

`analysis/map_regions.yaml` fixes three nested stored tile addresses and WGS84
viewports for each corpus source. The renderer validates nesting, square Web
Mercator views and archive bounds before drawing. It emits PNG/PDF panels,
`map_samples.tex`, a hash/selection manifest and a color key. New archives can use
automatic nonempty selection and generic styling; curate their YAML before using
them as article figures. Rendering reads local PMTiles directly, without a server.

## Frontend development

```sh
cd app/web
npm ci
npm test
npm run build
```

Rebuild the web image after editing it: `python manage.py build web` from the root,
then `python manage.py up`. Compose serves the built image and does not require
a pre-existing local `dist` directory.
