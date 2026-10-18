# From source maps to a Zenodo dataset

Run every command below from the **repository root**, the directory containing
`manage.py`. All input and output paths below are relative to this directory.

## Already have normalized maps and tile archives?

If the original sources, normalized GeoPackages and six PMTiles archives per
dataset already exist at the paths in `analysis/datasets.json`, skip conversion
and go directly to [statistics](#4-produce-statistics-and-inspect-checks):

```sh
python manage.py env
python manage.py download-sources --verify-only
python manage.py all
```

Review `docs/data/claims_report.md`, then use interactive export in step 6.
No Docker services or repeated conversion are needed to analyze ready-made files.
Keep existing normalization manifests with their GeoPackages when available.
Historical inputs may lack these manifests; the audit records missing provenance
rather than reconstructing it from assumptions.
Python 3.12–3.14, uv and Docker Compose v2 must be installed.

## 1. Prepare the environment

```sh
python manage.py env
python manage.py up
```

Open http://localhost:8080. Docker sees the local directory `app/data` as `/data`.
The five-source article analysis uses the fixed registry in
[`analysis/datasets.json`](../analysis/datasets.json); it does not automatically
analyze every file placed in a directory.

## 2. Place the original map files

For the article corpus, put the original files at these exact paths, relative to
the code repository root. Keep ZIP inputs compressed; the converter handles extraction.

| Dataset ID | Local original file |
|---|---|
| `natural_earth_vector` | `app/data/sources/natural_earth_vector/natural_earth_vector.gpkg.zip` |
| `usfws_luisiana_wetlands_geopackage` | `app/data/sources/usfws_luisiana_wetlands_geopackage/USFWS_Luisiana_wetlands_geopackage.zip` |
| `swisstopo_mountains_vector` | `app/data/sources/swisstopo_mountains_vector/Swisstopo_mountains_vector.zip` |
| `louisiana-260912` | `app/data/sources/louisiana-260912/louisiana-260912.osm.pbf` |
| `pdok_netherlands_infrostructure` | `app/data/sources/pdok_netherlands_infrostructure/pdok_Netherlands_infrostructure.zip` |

These IDs and filenames intentionally match the recorded experiment, including
their historical spelling. Verify the files:

```sh
python manage.py download-sources --verify-only
```

The command checks hashes and sizes from `analysis/sources.json`. The historical
acquisition URLs are incomplete: obtain matching originals as explained in
[Sources](sources.md). Placing a newer provider download under an old filename
does not reproduce the article input.

## 3. Normalize and generate tile pairs

For **each** of the five datasets, use the browser workflow:

1. Select local-file import and enter the corresponding container path, replacing
   `app/data/` with `/data/`. For example:
   `/data/sources/natural_earth_vector/natural_earth_vector.gpkg.zip`.
2. Use the exact dataset ID from the table above as the name. Review the proposed
   source layers, normalization bounds, dataset profile and zoom range. The saved
   corpus profiles are in `app/data/profiles/datasets/`; preserve the study settings
   when reproducing the article.
3. Run normalization (Stage A). Wait for successful completion.
4. Generate tiles from the normalized source (Stage B). Wait for all Standard,
   Dense-4 and Dense-16 MVT/MLT pairs. Inspect errors and validation diagnostics
   before proceeding. See [conversion settings](usage.md) for full validation mode.

For a dataset named `<id>`, the expected artifacts are:

```text
app/data/normalized/<id>/<id>.gpkg
app/data/normalized/<id>/<id>.normalization.json
app/data/profiles/datasets/<id>.yaml
app/data/output/<id>_standard_mvt.pmtiles
app/data/output/<id>_standard_mlt.pmtiles
app/data/output/<id>_dense4_mvt.pmtiles
app/data/output/<id>_dense4_mlt.pmtiles
app/data/output/<id>_dense16_mvt.pmtiles
app/data/output/<id>_dense16_mlt.pmtiles
```

Keep normalization manifests with their GeoPackages. Existing normalized sources
can be reused for Stage B. **`manage.py all` analyzes existing artifacts; it does
not download, normalize or tile missing maps.**

## 4. Produce statistics and inspect checks

After every registered dataset has its original input, normalized GPKG, profile
and six tile archives, run:

```sh
python manage.py all
```

This runs source profiling, normalized-source profiling, tile measurements,
full-pair/bounds audits, attribute-type analysis, SQL statistics and reporting.
It writes six SQLite databases and supporting CSV/JSON files into `docs/data`.
Read **`docs/data/claims_report.md`**: it contains executed queries, measured values,
failed checks and unresolved diagnostics. Do not interpret successful packaging
as proof that scientific checks passed. A failed report retains its diagnostics;
resolve or explicitly account for failures before publishing.

The detailed stages and optional codec-sensitivity measurements are described in
[Analysis](../analysis/README.md).

## 5. Generate images, if needed

```sh
python manage.py maps
```

Charts from reporting and curated map PNG/PDF panels are written into
`outputs/figures`; table fragments go into `outputs/tables`. Map selections are
configured in `analysis/map_regions.yaml`. This command is separate from dataset
packaging; map images are not automatically attached to the exported dataset.

## 6. Export the dataset

Stop running analysis/report writers before export. Run:

```sh
python manage.py
```

Choose **`6. export-dataset`**, then accept or change:

- Analysis directory: `docs/data`.
- Dataset export directory: `releases/dataset-v1`.

The equivalent command for unattended use is:

```sh
python manage.py export-dataset --input docs/data --output releases/dataset-v1
```

The destination must not already exist; choose another directory for the next
export. Successful export creates a self-contained upload package containing:

- Six SQLite snapshots, including `results.sqlite` for readers wanting one file.
- One `*_tables.zip` bundle per database, with corresponding Parquet and CSV tables.
- Report CSVs, chart inputs and the claims report.
- README, data dictionary, schema, source manifest, provenance and `SHA256SUMS`.

The original map files and PMTiles archives remain in `app/data`; they are not
copied into this package. `releases/` and generated data are ignored by Git.

## 7. Upload to Zenodo

Review the files in `releases/dataset-v1` and upload them separately to the
[dataset record](https://doi.org/10.5281/zenodo.23452598). Add selected map figures
separately if desired, preserving attribution. Uploading/publishing is a manual
step; export does not contact Zenodo. Follow [the release guide](releasing.md)
for record relationships, source terms and remaining provenance limitations.

## Using your own maps instead of the article corpus

An arbitrary map can be converted and previewed without entering the article
registry; try [the synthetic example](../examples/README.md). To include custom
maps in the analysis/export pipeline, edit `analysis/datasets.json` to list exactly
the intended dataset IDs, raw sources, normalized GPKGs, profiles and attribution.
Update `analysis/sources.json` with their actual source hashes, sizes and acquisition
metadata, and curate map regions/styles if figures are required. Custom inputs
produce a new experiment rather than a reproduction of the five-source article.
