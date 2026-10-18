# Publish software and data

## Software release

This directory is the standalone
[goodlancer-org/mvt-mlt-granularity](https://github.com/goodlancer-org/mvt-mlt-granularity)
repository. The article repository includes it as the `zenodo` Git submodule;
after cloning the article, run `git submodule update --init --recursive`.
No sibling article files are required.
`manage.py` is the only management entry point. There are no runtime dependencies
on the original checkout, its notebooks, Planetiler or the traffic study.

`uv.lock` pins the host environment; the converter has its own pinned requirements
and GDAL base image; `app/web/package-lock.json` pins frontend dependencies. Keep
these environments distinct in provenance. Container image tags and OS packages
are not bit-for-bit immutable environment snapshots.

```sh
python manage.py env
python manage.py test
uv run --frozen pytest
docker compose -f app/docker-compose.yml config --quiet
```

CI repeats Python checks on Windows/Linux and Python 3.12/3.14 and tests/builds the
frontend. The release workflow prepares a source archive as an Actions artifact.
After the authors publish a GitHub Release, the existing GitHub–Zenodo integration
archives the repository. `.zenodo.json` supplies software metadata and author
ORCIDs; `CITATION.cff` supplies citation metadata. Update the version and record
the assigned **software** DOI after publication. The dataset DOI is separate.

The project code uses the [MIT License](../LICENSE), also declared in
`.zenodo.json`, `CITATION.cff` and `pyproject.toml`. Third-party fonts, sprites,
map styles and source datasets retain their upstream terms.

Local verification on 18 October 2026: 22 analysis/export unittest tests and 159
converter pytest tests passed in the standalone Windows Python 3.13 environment;
142 frontend tests and the Vite production build passed. Both Docker images built.
A real three-point GeoJSON conversion produced all six archives with full pair
validation under Linux/Python 3.14.4/GDAL 3.13.3. The web root and datasets API
returned HTTP 200 through Compose. These checks do not constitute a fresh run of
the five-source article corpus or a completed GitHub Actions matrix run.

## Dataset release

```sh
python manage.py all
python manage.py maps
python manage.py export-dataset --output releases/dataset-v1
```

Read `claims_report.md`, not just the command exit status. Exporting is a packaging
operation, so diagnostic failures are retained rather than hidden. The exporter
requires all six SQLite files, a claims report and per-tile CSV, uses SQLite backup
to obtain each consistent snapshot, and writes all table formats from that snapshot.
Do not run measurement/report writers during export: snapshots are consistent
within a database, not a transaction spanning six independently written databases.

Upload the six SQLite files, six independent table bundles, root CSV/chart inputs,
README, dictionary/schema, source/provenance files and SHA256SUMS separately to
the [dataset record](https://doi.org/10.5281/zenodo.23452598). No single monolithic
ZIP is required; readers can download `results.sqlite` alone. The exporter rejects
more than 100 files. Map images can be attached separately with attribution;
original PMTiles are optional and carry source conditions.

Use `isDerivedFrom` links to the five providers, `isSupplementedBy` to the software
DOI, and `isSupplementTo` to the article once its identifier exists. The reserved
dataset DOI is not a software DOI. Complete licence and access metadata in Zenodo's
draft before publishing. [Zenodo metadata reference](https://developers.zenodo.org/).

## What remains a research/publication limitation

- Acquisition URLs and retrieval dates are missing from historical input records.
  Matching SHA-256 values are preserved, and the downloader can verify supplied files.
- Stable-feature-ID completeness and a second independent parser comparison are
  pending. Pair equality cannot establish either.
- `claims_report.md` links executable SQL to generated analytical numbers. Narrative
  claims, literature comparisons and the external traffic study are not validated
  by these measurements and require article review.
- Actual container builds and the five-source research run require Docker resources
  and the original maps. Tiny-fixture CI verifies code behavior, not the full corpus.
