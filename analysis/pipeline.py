"""File-based source, normalized-map and tile measurement pipeline."""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/data"
SQL = Path(__file__).parent / "sql"


def registry():
    return json.loads((Path(__file__).parent / "datasets.json").read_text(encoding="utf-8"))


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {"path": Path(path).relative_to(ROOT).as_posix(), "sha256": digest.hexdigest()}


def inputs_for(stage):
    datasets = registry()
    if stage == "sources":
        return [ROOT / d["source"] for d in datasets]
    if stage == "normalized":
        return [ROOT / d["normalized"] for d in datasets]
    if stage == "tiles":
        return [ROOT / "app/data/output" / f"{d['id']}_{v}_{f}.pmtiles"
                for d in datasets for v in ("standard", "dense4", "dense16") for f in ("mvt", "mlt")]
    if stage == 'types':
        return inputs_for('tiles')
    if stage == "audit":
        files = inputs_for('sources') + inputs_for('normalized') + inputs_for('tiles')
        files += [ROOT/d['profile'] for d in datasets]
        files += [ROOT/'app/converter/profiles/profile_rules.yaml', ROOT/'app/converter/config.yaml']
        files += [p.with_suffix('.normalization.json') for p in inputs_for('normalized') if p.with_suffix('.normalization.json').exists()]
        return [p for p in files if p.exists()]
    return [DATA / f"{s}_stats.sqlite" for s in ("source", "normalized", "tile")]


def stage_output(stage):
    return DATA / {"sources": "source_stats.sqlite", "normalized": "normalized_stats.sqlite",
                   "tiles": "tile_stats.sqlite", "audit": "audit_stats.sqlite", "types": "type_stats.sqlite", "stats": "results.sqlite"}[stage]


def manifest_inputs(stage):
    files = inputs_for(stage) + [Path(__file__)]
    if stage in ('sources','normalized'):
        files += [Path(__file__).parent/'map_analysis_core.py']
    elif stage == 'tiles':
        files += [Path(__file__).parent/'output_analysis_core.py']
    elif stage == 'types':
        files += [Path(__file__).parent/p for p in ('attribute_types.py', 'output_analysis_core.py')]
    elif stage == 'audit':
        files += [Path(__file__).parent/p for p in ('audit.py', 'map_analysis_core.py', 'output_analysis_core.py')]
        files += [ROOT/'app/converter/src'/p for p in ('profile_rules.py', 'semantic_taxonomy.py')]
    files += [Path(__file__).parent / "datasets.json"]
    if stage == "stats":
        files += sorted(SQL.glob("*.sql"))
        if (DATA/'audit_stats.sqlite').exists(): files += [DATA/'audit_stats.sqlite']
        if (DATA/'type_stats.sqlite').exists(): files += [DATA/'type_stats.sqlite']
    if stage == "normalized":
        files += [ROOT / d["profile"] for d in registry()]
    return [fingerprint(p) for p in files]


def describe(connection, stage, inputs):
    from .release import git
    from importlib.metadata import version
    from datetime import datetime, timezone
    import zlib
    connection.execute("CREATE TABLE IF NOT EXISTS main.meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT")
    values = {"schema_name": {"sources":"source_stats","normalized":"normalized_stats","tiles":"tile_stats","audit":"audit_stats","types":"type_stats","stats":"results"}[stage],
              "schema_version": "1" if stage in ('stats','audit','types') else "3", "tool": "analysis.pipeline", "tool_version":"0.3.0",
              "python": platform.python_version(), "inputs_json": json.dumps(inputs),
              "git_commit": git('rev-parse', 'HEAD') or 'unknown',
              "environment_json":json.dumps({'python':platform.python_version(),'zlib':zlib.ZLIB_RUNTIME_VERSION,
                  'packages':{p:version(p) for p in ['pyogrio','shapely','mapbox-vector-tile','maplibre-tiles','pandas','matplotlib']}}),
              "counting_semantics": "Source rows in S1/S3; tile feature instances in S6; streams per stored payload",
              "size_semantics": "gzip_payload_bytes = gzip.compress(raw, compresslevel=6, mtime=0); stored_bytes preserved"}
    connection.executemany("INSERT OR REPLACE INTO main.meta VALUES (?,?)", values.items())
    if not connection.execute("SELECT value FROM main.meta WHERE key='created_at_utc'").fetchone():
        timestamp = (connection.execute('SELECT generatedAt FROM analysis_meta').fetchone()[0]
                     if stage in ('sources','normalized') else datetime.now(timezone.utc).isoformat())
        connection.execute('INSERT INTO main.meta VALUES (?,?)',('created_at_utc',timestamp))


def profile(stage, target):
    from .map_analysis_core import rebuild_analysis
    paths = inputs_for(stage)
    rebuild_analysis(paths[0].parent, target, files=paths,
                     cache_dir=DATA / ".analysis_cache")
    with closing(sqlite3.connect(target)) as con, con:
        con.execute("CREATE TABLE dataset_files(dataset_id TEXT PRIMARY KEY, map_name TEXT, stage TEXT) STRICT")
        con.executemany("INSERT INTO dataset_files VALUES (?,?,?)",
                        [(d["id"], p.name, "raw" if stage == "sources" else "normalized")
                         for d, p in zip(registry(), paths)])
        # A geometry-less fallback must not be mistaken for a measured zero.
        con.execute("""UPDATE layers SET vertexCount=NULL WHERE EXISTS
            (SELECT 1 FROM analysis_errors e WHERE e.mapName=layers.mapName
             AND (e.layerName=layers.layerName OR e.layerName IS NULL))""")
        con.execute("UPDATE layers SET featureInstances=NULL WHERE featureInstances<0")
        con.execute("""UPDATE geometry_types SET vertexCount=NULL WHERE EXISTS
            (SELECT 1 FROM layers l WHERE l.mapName=geometry_types.mapName
              AND l.layerName=geometry_types.layerName AND l.vertexCount IS NULL)""")
        if stage == "normalized":
            normalized_extras(con, paths)


def normalized_extras(con, paths):
    import fnmatch
    import pyogrio
    import yaml
    from pyproj import Geod, Transformer
    con.executescript("""
      CREATE TABLE layer_mapping(dataset_id TEXT, source_layer TEXT, tile_layer TEXT,
        features INTEGER, vertices INTEGER, fields INTEGER);
      CREATE TABLE study_area(dataset_id TEXT, declared_bounds TEXT, actual_extent TEXT,
        area_km2 REAL, bounds_ok INTEGER, status TEXT);
    """)
    for d, path in zip(registry(), paths):
        profile = yaml.safe_load((ROOT / d["profile"]).read_text(encoding="utf-8"))
        for layer, features, vertices, fields in con.execute(
                "SELECT layerName,featureInstances,vertexCount,fieldCount FROM layers WHERE mapName=?", (path.name,)).fetchall():
            matches = [t["id"] for t in profile["tile_layers"] if
                       layer in t.get("source_layers", []) or any(fnmatch.fnmatchcase(layer, p)
                       for p in t.get("source_layer_prefixes", []))]
            for match in matches or [None]:
                con.execute("INSERT INTO layer_mapping VALUES (?,?,?,?,?,?)",
                            (d["id"], layer, match, features, vertices, fields))
        bounds = profile.get("output", {}).get("bounds")
        extents = []
        for name, kind in pyogrio.list_layers(path):
            if not kind:
                continue
            info = pyogrio.read_info(path, layer=name, force_total_bounds=True)
            b = info.get("total_bounds")
            if b is not None and all(__import__('math').isfinite(float(v)) for v in b):
                extents.append(Transformer.from_crs(info["crs"], 4326, always_xy=True).transform_bounds(*b))
        actual = ([min(b[0] for b in extents), min(b[1] for b in extents),
                   max(b[2] for b in extents), max(b[3] for b in extents)] if extents else None)
        area = None
        ok = None
        if bounds and actual:
            a,b,c,e = bounds
            area = abs(Geod(ellps="WGS84").polygon_area_perimeter([a,c,c,a], [b,b,e,e])[0])/1e6
            tol = 1e-5
            ok = int(actual[0]>=a-tol and actual[1]>=b-tol and actual[2]<=c+tol and actual[3]<=e+tol)
        con.execute("INSERT INTO study_area VALUES (?,?,?,?,?,?)",
                    (d["id"], json.dumps(bounds), json.dumps(actual), area, ok,
                     "checked" if ok is not None else "missing_declared_bounds_or_extent"))


def tile_extras(target, codec_sensitivity=False):
    from . import output_analysis_core as core
    with closing(sqlite3.connect(target)) as con, con:
        con.executescript("""
          ALTER TABLE tiles ADD COLUMN logical_zoom INTEGER;
          UPDATE tiles SET logical_zoom=z+(SELECT CASE m.density_factor WHEN 4 THEN 1 WHEN 16 THEN 2 ELSE 0 END
            FROM archives a JOIN maps m ON m.id=a.map_id WHERE a.id=tiles.archive_id);
          CREATE TABLE gzip_check AS SELECT m.dataset_name AS dataset_id,m.variant,a.format,
            COUNT(*) AS n_tiles,SUM(t.stored_bytes=t.gzip_payload_bytes) AS n_equal,
            SUM(t.stored_bytes) AS sum_stored,SUM(t.gzip_payload_bytes) AS sum_gzip6,
            MAX(ABS(t.stored_bytes-t.gzip_payload_bytes)) AS max_abs_diff
            FROM tiles t JOIN archives a ON a.id=t.archive_id JOIN maps m ON m.id=a.map_id
            GROUP BY m.dataset_name,m.variant,a.format;
          CREATE TABLE parser_checks AS SELECT a.map_id,a.id AS archive_id,
            COUNT(*) AS layer_frames,SUM(l.parse_error IS NOT NULL) AS failed_frames,
            SUM(l.raw_frame_bytes) AS frame_bytes,
            SUM(l.stream_payload_bytes+l.stream_overhead_bytes) AS stream_bytes
            FROM mlt_layers l JOIN archives a ON a.id=l.archive_id GROUP BY a.id;
        """)
        if codec_sensitivity:
            import brotli
            import zstandard
            con.execute("CREATE TABLE codec_sizes(archive_id INTEGER, content_offset INTEGER, stored_bytes INTEGER, gzip9_bytes INTEGER, brotli11_bytes INTEGER, zstd19_bytes INTEGER, PRIMARY KEY(archive_id,content_offset,stored_bytes)) STRICT")
            import gzip
            for aid, path in con.execute("SELECT id,path FROM archives").fetchall():
                header = core.read_pmtiles_header(path)
                seen = set()
                with Path(path).open("rb") as handle:
                    for run in core._iter_tile_runs_from_handle(handle, header):
                        key = (run.offset, run.length)
                        if key in seen:
                            continue
                        seen.add(key)
                        raw = core._decompress(core._read_section(handle, header.tile_data_offset+run.offset, run.length), header.tile_compression, path)
                        con.execute("INSERT INTO codec_sizes VALUES (?,?,?,?,?,?)", (aid,*key,
                            len(gzip.compress(raw,compresslevel=9,mtime=0)),len(brotli.compress(raw,quality=11)),
                            len(zstandard.ZstdCompressor(level=19).compress(raw))))


def statistics(target):
    with closing(sqlite3.connect(target, uri=True)) as con, con:
        for alias, name in (("tile", "tile_stats"), ("raw", "source_stats"), ("norm", "normalized_stats")):
            con.execute(f"ATTACH DATABASE ? AS {alias}", ((DATA / f"{name}.sqlite").as_uri()+"?mode=ro",))
        for (name,) in con.execute("SELECT name FROM tile.sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'").fetchall():
            con.execute(f'CREATE TEMP VIEW "{name}" AS SELECT * FROM tile."{name}"')
        for path in sorted(SQL.glob("[0-9]*.sql")):
            print(f"Statistics: {path.name}", flush=True)
            con.executescript(path.read_text(encoding="utf-8"))
        for stage, alias in (("raw", "raw"), ("normalized", "norm")):
            con.execute(f"""CREATE TABLE {stage}_structure AS SELECT d.dataset_id,m.sourceFormat,
              m.fileBytes,COUNT(l.layerName) AS layers,
              CASE WHEN COUNT(l.featureInstances)=COUNT(l.layerName) THEN SUM(l.featureInstances) END AS features,
              CASE WHEN COUNT(l.vertexCount)=COUNT(l.layerName) THEN SUM(l.vertexCount) END AS vertices,
              SUM(l.fieldCount) AS fields,
              (SELECT COUNT(DISTINCT fieldName) FROM {alias}.layer_fields f WHERE f.mapName=m.mapName) AS distinct_fields,m.errorCount
              FROM {alias}.dataset_files d JOIN {alias}.maps m ON m.mapName=d.map_name
              LEFT JOIN {alias}.layers l ON l.mapName=m.mapName GROUP BY d.dataset_id""")
        for table in ("layer_mapping", "study_area"):
            con.execute(f"CREATE TABLE {table} AS SELECT * FROM norm.{table}")
        for table in ("gzip_check", "parser_checks", "pair_validation", "analysis_errors"):
            con.execute(f"CREATE TABLE main.{table} AS SELECT * FROM tile.{table}")
        if (DATA/'audit_stats.sqlite').exists():
            con.execute('ATTACH DATABASE ? AS audit', ((DATA/'audit_stats.sqlite').as_uri()+'?mode=ro',))
            for table in ('bounds','bounds_checks','validation','validation_issues'):
                con.execute(f'CREATE TABLE main.{table} AS SELECT * FROM audit.{table}')
        if (DATA/'type_stats.sqlite').exists():
            from .attribute_types import TABLES
            con.execute('ATTACH DATABASE ? AS types', ((DATA/'type_stats.sqlite').as_uri()+'?mode=ro',))
            for table in TABLES:
                con.execute(f'CREATE TABLE main.{table} AS SELECT * FROM types.{table}')
        if con.execute("SELECT COUNT(*) FROM tile.sqlite_master WHERE name='codec_sizes'").fetchone()[0]:
            con.execute("""CREATE TABLE codec_summary AS SELECT m.dataset_name AS dataset_id,m.variant,a.format,
                SUM(c.gzip9_bytes) AS gzip9_bytes,SUM(c.brotli11_bytes) AS brotli11_bytes,
                SUM(c.zstd19_bytes) AS zstd19_bytes,'address_weighted' AS weighting
                FROM tile.codec_sizes c JOIN tile.tiles t ON t.archive_id=c.archive_id
                  AND t.content_offset=c.content_offset AND t.stored_bytes=c.stored_bytes
                JOIN tile.archives a ON a.id=t.archive_id JOIN tile.maps m ON m.id=a.map_id
                GROUP BY m.dataset_name,m.variant,a.format""")
            con.execute("""CREATE TABLE codec_gain AS WITH savings AS (
                SELECT m.dataset_id,m.variant,
                  100.0*(1-l.gzip9_bytes*1.0/NULLIF(m.gzip9_bytes,0)) AS s_gzip9,
                  100.0*(1-l.brotli11_bytes*1.0/NULLIF(m.brotli11_bytes,0)) AS s_brotli11,
                  100.0*(1-l.zstd19_bytes*1.0/NULLIF(m.zstd19_bytes,0)) AS s_zstd19
                FROM codec_summary m JOIN codec_summary l USING(dataset_id,variant)
                WHERE m.format='MVT' AND l.format='MLT')
                SELECT v.*,v.s_gzip9-s.s_gzip9 AS g_gzip9,v.s_brotli11-s.s_brotli11 AS g_brotli11,
                  v.s_zstd19-s.s_zstd19 AS g_zstd19 FROM savings v JOIN savings s USING(dataset_id)
                WHERE s.variant='standard'""")
        import pandas as pd
        con.execute("CREATE TABLE tile_correlation(dataset_id TEXT,measure TEXT,predictor TEXT,n_tiles INTEGER,spearman_rho REAL,weighting TEXT)")
        for d in registry():
            frame = pd.read_sql_query("SELECT feature_instances,vertex_count,mvt_raw_bytes,mlt_raw_bytes,mvt_gzip_bytes,mlt_gzip_bytes FROM v_tile_comparison WHERE dataset_name=?", con, params=(d["id"],))
            for measure, mvt, mlt in (("raw","mvt_raw_bytes","mlt_raw_bytes"),("gzip6","mvt_gzip_bytes","mlt_gzip_bytes")):
                saving = 1-frame[mlt]/frame[mvt].replace(0,float('nan'))
                for predictor in ("feature_instances","vertex_count"):
                    valid = pd.DataFrame({"saving":saving,"predictor":frame[predictor]}).dropna()
                    rho = (valid['saving'].rank().corr(valid['predictor'].rank())
                           if len(valid)>1 and valid['saving'].nunique()>1 and valid['predictor'].nunique()>1 else None)
                    con.execute("INSERT INTO tile_correlation VALUES (?,?,?,?,?,?)", (d['id'],measure,predictor,len(valid),rho,'address_weighted'))


def run_stage(stage, force=False, codec_sensitivity=False):
    DATA.mkdir(parents=True, exist_ok=True)
    target = stage_output(stage)
    manifest = target.with_suffix(".sqlite.manifest.json")
    print(f"Checking inputs: {stage}", flush=True)
    inputs = manifest_inputs(stage)
    parameters = {"codec_sensitivity": codec_sensitivity if stage == "tiles" else False}
    if not force and target.exists() and manifest.exists():
        old = json.loads(manifest.read_text(encoding="utf-8"))
        if old["inputs"] == inputs and old["parameters"] == parameters and old["output"] == fingerprint(target):
            print(f"Up to date: {target}", flush=True)
            return
    temporary = target.with_suffix(".sqlite.partial")
    if temporary.exists():
        temporary.unlink()
    print(f"Building: {stage}", flush=True)
    if stage in ("sources", "normalized"):
        profile(stage, temporary)
    elif stage == "tiles":
        from .output_analysis_core import build_analysis_database
        build_analysis_database(ROOT / "app/data/output", temporary, progress=lambda s: print(s, flush=True),
            pair_names={f"{d['id']}_{v}" for d in registry() for v in ('standard','dense4','dense16')})
        tile_extras(temporary, codec_sensitivity)
    elif stage == 'audit':
        from .audit import build
        build(temporary, ROOT, DATA, registry())
    elif stage == 'types':
        from .attribute_types import build
        build(temporary, ROOT, registry())
    else:
        statistics(temporary)
    with closing(sqlite3.connect(temporary)) as con, con:
        describe(con, stage, inputs)
    os.replace(temporary, target)
    record = {"stage": stage, "inputs": inputs, "parameters": parameters, "output": fingerprint(target)}
    part = manifest.with_suffix(".json.partial")
    part.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(part, manifest)
    print(f"Written: {target}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["sources", "normalized", "tiles", "audit", "types", "stats", "report", "all"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--codec-sensitivity", action="store_true")
    args = parser.parse_args(argv)
    stages = ["sources", "normalized", "tiles", "audit", "types", "stats", "report"] if args.stage == "all" else [args.stage]
    for stage in stages:
        if stage == "report":
            from .report import report
            try:
                report()
            except RuntimeError as error:
                print(str(error), flush=True)
                return 1
        else:
            run_stage(stage, args.force, args.codec_sensitivity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
