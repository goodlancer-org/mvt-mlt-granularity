"""Handing one source to ogr2ogr, fast, when the GeoPackage already exists.

`-skipfailures` makes GDAL override -gt to 1, so every feature gets its own
SQLite transaction and every commit fsyncs. Free while the output is being
created, ruinous once it exists. Measured on a 33 MB source into a GeoPackage
holding one 64 KB layer:

    append, -skipfailures                72 s
    append, no -skipfailures              1 s
    append, -skipfailures + SYNC OFF      3 s
    create, -skipfailures                 3 s

So the flag is not paid up front: a source is converted strictly, and only one
that actually fails is retried tolerantly. A dropped feature becomes a recorded
event rather than a silent one, which is what lets per-layer feature counts be
quoted in the paper.
"""


def append_attempts(
    target_gpkg,
    source,
    layer_name,
    source_srs=None,
    source_open_options=None,
    gpkg_exists=False,
    retry_replaces_layer=True,
    clip_bounds=None,
    clip_bounds_srs="EPSG:4326",
):
    """The ordered ogr2ogr invocations for one source: strict, then tolerant.

    retry_replaces_layer: True when one source owns one layer, so overwriting is
        the cleanest way to discard a half-written layer. False when many sources
        share one layer (the Groundswell merge), where overwriting would destroy
        everything already merged — those callers delete their own rows first.
    """
    def build(mode, tolerate_failures):
        cmd = ["ogr2ogr"]
        if tolerate_failures:
            # -skipfailures pins -gt to 1, so this pass commits once per feature.
            # 72 s with synchronous writes against 3 s without, same source. The
            # scratch GeoPackage is disposable, so durability buys nothing.
            cmd += ["--config", "OGR_SQLITE_SYNCHRONOUS", "OFF"]
        cmd += ["-f", "GPKG"]
        if mode == "append":
            cmd += ["-update", "-append"]
        elif mode == "replace":
            cmd += ["-update", "-overwrite"]
        for opt in (source_open_options or []):
            cmd += ["-oo", str(opt)]
        if source_srs:
            cmd += ["-s_srs", source_srs]
        cmd += [str(target_gpkg), str(source), "-nln", layer_name]
        if clip_bounds and len(clip_bounds) == 4:
            min_x, min_y, max_x, max_y = clip_bounds
            cmd += [
                "-spat_srs", str(clip_bounds_srs),
                "-spat", str(min_x), str(min_y), str(max_x), str(max_y),
            ]
        cmd += ["-t_srs", "EPSG:4326", "-nlt", "CONVERT_TO_LINEAR"]
        if tolerate_failures:
            cmd.append("-skipfailures")
        return cmd

    if not gpkg_exists:
        return [build("create", False), build("create", True)]
    retry_mode = "replace" if retry_replaces_layer else "append"
    return [build("append", False), build(retry_mode, True)]
