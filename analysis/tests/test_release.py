"""Round-trip releases and checksum failures using small synthetic measurements."""
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import zipfile

import pyarrow.parquet as pq

from analysis import release
from analysis.tests.test_pipeline import fixture_directory


class ReleaseTest(unittest.TestCase):
    def test_snapshots_csv_parquet_checksums_and_no_overwrite(self):
        with fixture_directory() as root:
            data = root/'data'
            data.mkdir()
            for name in release.DATABASES:
                with closing(sqlite3.connect(data/f'{name}.sqlite')) as con, con:
                    con.executescript('CREATE TABLE measurements(id INTEGER, size_bytes INTEGER, note TEXT); CREATE TABLE empty(value REAL);')
                    con.executemany('INSERT INTO measurements VALUES(?,?,?)', [(1, 2**60+1, ''), (2, None, 'wetlands')])
            from analysis import tile_store
            with closing(tile_store.Connection()) as tiles:
                tiles.executescript('CREATE TABLE measurements(id BIGINT, size_bytes BIGINT, note TEXT); CREATE TABLE empty(value DOUBLE);')
                tiles.executemany('INSERT INTO measurements(id,size_bytes,note) VALUES (?,?,?)', [(1, 2**60+1, ''), (2,None,'wetlands')])
                tile_store.write(tiles, data/'tile_stats', 'CREATE TABLE measurements(id INTEGER, size_bytes INTEGER, note TEXT); CREATE TABLE empty(value REAL);')
            (data/'claims_report.md').write_text('# Synthetic checks\n')
            (data/'per_tile.csv').write_text('z,x,y\n0,0,0\n')
            result = release.export_dataset(data, root/'release')
            with zipfile.ZipFile(result/'results_tables.zip') as bundle:
                table = pq.read_table(io.BytesIO(bundle.read('measurements.parquet')))
                self.assertEqual(table.to_pylist(), [dict(id=1,size_bytes=2**60+1,note=''), dict(id=2,size_bytes=None,note='wetlands')])
                empty = pq.read_table(io.BytesIO(bundle.read('empty.parquet')))
                self.assertEqual(empty.num_rows, 0)
                self.assertEqual(str(empty.schema.field('value').type), 'double')
                self.assertTrue(bundle.read('measurements.csv').startswith(b'id,size_bytes,note'))
            self.assertFalse((result/'tile_stats.sqlite').exists())
            self.assertFalse((result/'tile_stats_tables.zip').exists())
            with zipfile.ZipFile(result/'tile_stats_parquet.zip') as bundle:
                self.assertEqual(set(bundle.namelist()), {'measurements.parquet','empty.parquet','schema.sql','schema.json'})
                table = pq.read_table(io.BytesIO(bundle.read('measurements.parquet')))
                self.assertEqual(table.to_pylist(), [dict(id=1,size_bytes=2**60+1,note=''),dict(id=2,size_bytes=None,note='wetlands')])
            for line in (result/'SHA256SUMS').read_text().splitlines():
                expected, name = line.split('  ', 1)
                self.assertEqual(release.sha256(result/name), expected)
            with self.assertRaises(FileExistsError):
                release.export_dataset(data, result)
            self.assertLess(len(list(result.rglob('*'))), 100)
            schema_path = data/'tile_stats/schema.json'
            schema = json.loads(schema_path.read_text())
            schema['measurements']['rows'] += 1
            schema_path.write_text(json.dumps(schema))
            with self.assertRaisesRegex(ValueError, 'schema/row count mismatch'):
                release.export_dataset(data, root/'bad-release')
            self.assertFalse((root/'bad-release').exists())

    def test_bad_download_never_becomes_a_source(self):
        with fixture_directory() as root:
            manifest = root/'sources.json'
            manifest.write_text(json.dumps([dict(dataset_id='tiny', path='source.zip', url='https://example.org/source', sha256='0'*64, size_bytes=None)]))
            with patch.object(release, 'urlopen', return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    release.download_sources(manifest, root)
            self.assertFalse((root/'source.zip').exists())

    def test_missing_sources_and_escaping_manifest_are_refused(self):
        with fixture_directory() as root:
            manifest = root/'sources.json'
            manifest.write_text(json.dumps([dict(dataset_id='tiny', path='missing.zip', url=None, sha256='0'*64)]))
            with self.assertRaises(FileNotFoundError):
                release.download_sources(manifest, root)
            manifest.write_text(json.dumps([dict(path='../escape.zip')]))
            with self.assertRaisesRegex(ValueError, 'escapes'):
                release.download_sources(manifest, root)
