# Pipeline reference

The standalone workflows are documented in [conversion and preview](usage.md)
and [analysis](../analysis/README.md).

Stage A creates a canonical XY-only EPSG:3857 GeoPackage with spatial indexes,
physical bounds clipping and a normalization manifest. Stage B generates one MVT
MBTiles archive per variant with GDAL, repacks it to PMTiles and transcodes the
same tile payloads to MLT. MBTiles is a temporary container, not a measured
research output.

The analysis pipeline profiles raw/normalized sources, measures addresses and
unique payloads, audits decoded pairs, traces attribute types, materializes SQL
metrics and renders tables/figures. See the [data dictionary](data_dictionary.md)
for grain, units and NULL rules, and the [schema catalogue](schema.md) for columns.

[Release packaging](releasing.md) produces independent SQLite files and one
Parquet/CSV table bundle per database, with checksums and provenance.
