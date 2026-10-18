"""Export Parquet tile measurements and five SQLite snapshots for Zenodo."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATABASES = ('results', 'source_stats', 'normalized_stats', 'audit_stats', 'type_stats')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def git(*args):
    try:
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def export_tables(database, destination):
    """Stream all tables with explicit Arrow schemas, preserving NULL and integers."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    destination.mkdir(parents=True)
    schema = {}
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as con:
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
            columns = con.execute(f'PRAGMA table_info({quote(table)})').fetchall()
            # CTAS expressions may have no declared affinity: inspect SQLite types,
            # never infer from the first chunk (which may contain only NULL).
            fields = []
            descriptions = []
            for _, name, declared, notnull, default, pk in columns:
                kinds = {r[0] for r in con.execute(f'SELECT DISTINCT typeof({quote(name)}) FROM {quote(table)}')}
                kinds.discard('null')
                if kinds <= {'integer'} and (kinds or 'INT' in declared.upper() or 'BOOL' in declared.upper()):
                    dtype = pa.int64()
                elif kinds <= {'integer', 'real'} and (kinds or any(t in declared.upper() for t in ('REAL', 'DOUBLE', 'FLOAT'))):
                    dtype = pa.float64()
                elif kinds <= {'blob'} and kinds:
                    dtype = pa.binary()
                elif kinds <= {'text'} or not kinds:
                    dtype = pa.string()
                else:
                    raise ValueError(f'Mixed SQLite storage types in {table}.{name}: {kinds}')
                fields.append(pa.field(name, dtype))
                descriptions.append(dict(name=name, sqlite_type=declared, parquet_type=str(dtype),
                                         nullable=not bool(notnull), primary_key=bool(pk)))
            arrow_schema = pa.schema(fields)
            count = 0
            with (destination/f'{table}.csv').open('w', encoding='utf-8', newline='') as stream, pq.ParquetWriter(destination/f'{table}.parquet', arrow_schema, compression='zstd') as writer:
                csv_writer = csv.writer(stream)
                csv_writer.writerow([c[1] for c in columns])
                cursor = con.execute(f'SELECT * FROM {quote(table)}')
                while rows := cursor.fetchmany(65536):
                    csv_writer.writerows(rows)
                    writer.write_table(pa.Table.from_arrays([
                        pa.array([row[i] for row in rows], type=field.type)
                        for i, field in enumerate(fields)], schema=arrow_schema))
                    count += len(rows)
            schema[table] = dict(rows=count, columns=descriptions)
    return schema


def export_dataset(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite release directory: {output}')
    if source == output or source in output.parents:
        raise ValueError('Release directory must be outside its input directory')
    for name in DATABASES:
        if not (source/f'{name}.sqlite').is_file():
            raise FileNotFoundError(source/f'{name}.sqlite')
    required = ('claims_report.md', 'per_tile.csv', 'tile_stats/schema.json', 'tile_stats/schema.sql')
    for name in required:
        if not (source/name).is_file():
            raise FileNotFoundError(source/name)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dataset-', dir=output.parent) as work:
        staging = Path(work)/'release'
        staging.mkdir()
        schemas = {}
        for name in DATABASES:
            target = staging/f'{name}.sqlite'
            with closing(sqlite3.connect((source/f'{name}.sqlite').as_uri()+'?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError(f'Integrity check failed: {name}')
            schemas[name] = export_tables(target, staging/'tables'/name)
            # Independently downloadable table bundles keep a release below
            # Zenodo's file-count limit without one monolithic dataset archive.
            table_dir = staging/'tables'/name
            with zipfile.ZipFile(staging/f'{name}_tables.zip', 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(table_dir.iterdir()):
                    bundle.write(path, path.name)
            if table_dir.resolve().parent != (staging/'tables').resolve():
                raise RuntimeError('Table cleanup escaped staging directory')
            shutil.rmtree(table_dir)
        (staging/'tables').rmdir()
        # Tile measurements are Parquet-only; never recreate a SQLite snapshot.
        import pyarrow.parquet as pq
        tile_dir = source/'tile_stats'
        schemas['tile_stats'] = json.loads((tile_dir/'schema.json').read_text())
        if not schemas['tile_stats']:
            raise ValueError('Empty tile schema catalogue')
        from .tile_store import connect
        with closing(connect(tile_dir)):
            pass
        with zipfile.ZipFile(staging/'tile_stats_parquet.zip', 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            for table, expected in sorted(schemas['tile_stats'].items()):
                if Path(table).name != table:
                    raise ValueError(f'Invalid table name: {table}')
                path = tile_dir/f'{table}.parquet'
                pf = pq.ParquetFile(path)
                if pf.metadata.num_rows != expected['rows'] or pf.schema_arrow.names != [c['name'] for c in expected['columns']] or [str(f.type) for f in pf.schema_arrow] != [c['parquet_type'] for c in expected['columns']]:
                    raise ValueError(f'Parquet schema/row count mismatch: {table}')
                bundle.write(path, path.name)
            for filename in ('schema.sql', 'schema.json'):
                bundle.write(tile_dir/filename, filename)
        # Copy report/figure inputs, never caches, logs or partial databases.
        for pattern in ('*.csv', '*.dat', '*.json', '*.md'):
            for path in source.glob(pattern):
                shutil.copy2(path, staging/path.name)
        (staging/'schema.json').write_text(json.dumps(schemas, indent=2)+'\n', encoding='utf-8')
        for name, filename in (('data_dictionary.md', 'DATA_DICTIONARY.md'), ('sources.md', 'SOURCES.md')):
            shutil.copy2(ROOT/'docs'/name, staging/filename)
        shutil.copy2(ROOT/'docs/schema.md', staging/'schema.md')
        shutil.copy2(ROOT/'analysis/sources.json', staging/'sources.json')
        shutil.copy2(ROOT/'docs/dataset.md', staging/'README.md')
        packages = {}
        for name in ('mapbox-vector-tile', 'maplibre-tiles', 'pmtiles', 'pyogrio', 'shapely', 'pyarrow', 'pandas', 'brotli', 'zstandard', 'duckdb'):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = None
        converter = ROOT/'app/converter/config.yaml'
        provenance = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), git_commit=git('rev-parse', 'HEAD'),
                          git_tag=git('describe', '--tags', '--exact-match'), git_dirty=bool(git('status', '--porcelain')),
                          python=platform.python_version(), export_environment=packages,
                          converter_config_sha256=sha256(converter),
                          note='Export package versions describe this export environment. Measurement/encoder environments remain in database meta, input manifests and conversion protocols; unknown versions are not inferred.')
        provenance['distribution'] = {'tile_stats': {'archive': 'tile_stats_parquet.zip', 'format': 'Parquet (Zstandard), one file per table, with schema.sql and schema.json', 'tables': len(schemas['tile_stats']), 'rows': sum(t['rows'] for t in schemas['tile_stats'].values()), 'sqlite_snapshot': False}}
        # Keep actual conversion environments when available; do not claim that
        # the export environment produced the historical measurements.
        protocols = staging/'conversion_protocols'
        for path in sorted((ROOT/'app/data/protocols').glob('*.json')):
            protocols.mkdir(exist_ok=True)
            shutil.copy2(path, protocols/path.name)
        (staging/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n', encoding='utf-8')
        files = sorted(p for p in staging.rglob('*') if p.is_file())
        if len(files) + 1 > 100:
            raise ValueError(f'Release has {len(files)+1} files; exceeds 100-file publication budget')
        (staging/'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.relative_to(staging).as_posix()}\n' for p in files), encoding='utf-8')
        staging.rename(output)
    return output


def download_sources(manifest, root=ROOT, verify_only=False):
    root = Path(root).resolve()
    for entry in json.loads(Path(manifest).read_text(encoding='utf-8')):
        target = (root/entry['path']).resolve()
        if root not in target.parents:
            raise ValueError('Source destination escapes repository')
        if not target.exists():
            if verify_only or not entry.get('url'):
                raise FileNotFoundError(f"{target}: supply the exact source or a verified URL in {manifest}")
            if not entry['url'].startswith('https://'):
                raise ValueError('Source downloads require HTTPS')
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                with urlopen(entry['url'], timeout=120) as response, temporary.open('wb') as stream:
                    shutil.copyfileobj(response, stream)
                verify_source(temporary, entry)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        verify_source(target, entry)
        print(f"Verified: {entry['dataset_id']}")


def verify_source(path, entry):
    if sha256(path) != entry['sha256']:
        raise ValueError(f'SHA-256 mismatch: {path}')
    if entry.get('size_bytes') is not None and path.stat().st_size != entry['size_bytes']:
        raise ValueError(f'Size mismatch: {path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export-dataset')
    export.add_argument('--input', type=Path, default=ROOT/'docs/data')
    export.add_argument('--output', type=Path, required=True)
    download = commands.add_parser('download-sources')
    download.add_argument('--manifest', type=Path, default=ROOT/'analysis/sources.json')
    download.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'export-dataset':
        print(export_dataset(args.input, args.output))
    else:
        download_sources(args.manifest, verify_only=args.verify_only)


if __name__ == '__main__':
    main()
